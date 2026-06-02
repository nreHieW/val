import concurrent.futures
import logging
import os
import threading
import time
import traceback
from collections import Counter

import pandas as pd
from pymongo import UpdateOne

from scrape.core.config import DCF_MAX_WORKERS, MARKETSCREENER_MAX_WORKERS, TICKER_TIMEOUT_SECONDS
from scrape.core.http_utils import run_with_timeout
from scrape.core.json_util import normalize_json
from scrape.core.mongo import get_mongo_client
from scrape.core.tickers import get_all_tickers
from scrape.sources.marketscreener import load_marketscreener_cache, log_marketscreener_stats, save_marketscreener_cache
from scrape.sources.yahoo_market_discovery import get_sector_industries, get_similar_companies
from scrape.sources.yahoo_profiles import compute_ttm_financials, get_and_parse_yahoo, prefetch_sec_ttm_financials
from scrape.sources.yahoo_snapshot import get_yahoo_snapshots
from scrape.valuation.dcf_inputs import MissingFinancialStatements, get_dcf_inputs
from scrape.valuation.market_metrics import (
    get_10year_tbill,
    get_country_erp,
    get_exchange_rates,
    get_industry_avgs,
    get_mature_erp,
)
from scrape.valuation.string_mapper import StringMapper

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s: %(message)s")
logging.getLogger("yahooquery").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _log_timing(label, fn, *args, **kwargs):
    started = time.monotonic()
    try:
        return fn(*args, **kwargs)
    finally:
        logger.info("%s completed in %.1fs", label, time.monotonic() - started)


def _log_dcf_progress(batch, total_batches, completed_tickers, total_tickers, started):
    elapsed = time.monotonic() - started
    throughput = completed_tickers / elapsed if elapsed else 0
    logger.info(
        "Processing batch %s of %s: %s of %s tickers completed in %.1fs (%.2f tickers/s)",
        batch,
        total_batches,
        completed_tickers,
        total_tickers,
        elapsed,
        throughput,
    )


def _log_ticker_exception(label, ticker, error):
    tb = traceback.extract_tb(error.__traceback__)
    if tb:
        frame = tb[-1]
        reason = f"{type(error).__name__} at {os.path.relpath(frame.filename)}:{frame.lineno} in {frame.name}"
    else:
        reason = type(error).__name__
    logger.warning("%s failed for %s: %s", label, ticker, reason)
    logger.debug("%s failed for %s\n%s", label, ticker, "".join(traceback.format_exception(type(error), error, error.__traceback__)))
    return reason


def _get_ticker_chunk(tickers):
    chunk_count = int(os.getenv("SCRAPE_CHUNK_COUNT", "1"))
    chunk_index = int(os.getenv("SCRAPE_CHUNK_INDEX", "0"))
    if chunk_count < 1:
        raise ValueError("SCRAPE_CHUNK_COUNT must be at least 1")
    if not 0 <= chunk_index < chunk_count:
        raise ValueError("SCRAPE_CHUNK_INDEX must be between 0 and SCRAPE_CHUNK_COUNT - 1")

    configured_chunk_size = os.getenv("SCRAPE_CHUNK_SIZE")
    chunk_size = int(configured_chunk_size) if configured_chunk_size else (len(tickers) + chunk_count - 1) // chunk_count
    if chunk_size < 1:
        raise ValueError("SCRAPE_CHUNK_SIZE must be at least 1")
    if len(tickers) > chunk_count * chunk_size:
        raise ValueError("Ticker count exceeds configured scrape chunk capacity")
    start = chunk_index * chunk_size
    chunk = tickers[start : start + chunk_size]
    logger.info("Ticker chunk %s of %s loaded: %s tickers", chunk_index + 1, chunk_count, len(chunk))
    return chunk


def run_dcf_scrape(tickers, client, yahoo_snapshots=None):
    yahoo_snapshots = yahoo_snapshots or {}
    logger.info("Running DCF scrape for %s tickers", len(tickers))
    country_erps = get_country_erp()
    region_mapper = StringMapper(list(country_erps.keys()))
    avg_metrics = get_industry_avgs()
    avg_betas = avg_metrics["Unlevered Beta"]
    industry_mapper = StringMapper(list(avg_betas.keys()))
    risk_free_rate = get_10year_tbill()
    mature_erp = get_mature_erp()
    fx_rates = get_exchange_rates()

    db_name = os.getenv("MONGODB_DB_NAME")
    dcf_db = client[db_name]["dcf_inputs"]
    overview_db = client[db_name]["ticker_overviews"]
    failure_counts = Counter()
    skipped_counts = Counter()
    yahoo_profiles = {}
    yahoo_overviews = {}
    dcf_records = []
    marketscreener_forecast_failures = Counter()
    marketscreener_forecast_failure_samples = {}
    processing_started = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=DCF_MAX_WORKERS) as executor, concurrent.futures.ThreadPoolExecutor(max_workers=MARKETSCREENER_MAX_WORKERS) as marketscreener_executor:
        ticker_iter = iter(tickers)
        futures = {}

        def submit_next_ticker():
            try:
                ticker = next(ticker_iter)
            except StopIteration:
                return False
            futures[
                executor.submit(
                    process_ticker,
                    ticker,
                    country_erps,
                    region_mapper,
                    avg_metrics,
                    industry_mapper,
                    mature_erp,
                    risk_free_rate,
                    fx_rates,
                    yahoo_snapshots.get(ticker),
                    marketscreener_executor,
                )
            ] = ticker
            return True

        for _ in range(min(DCF_MAX_WORKERS, len(tickers))):
            submit_next_ticker()

        total_batches = (len(tickers) + DCF_MAX_WORKERS - 1) // DCF_MAX_WORKERS
        if futures:
            _log_dcf_progress(1, total_batches, 0, len(tickers), processing_started)

        completed_tickers = 0
        next_batch_to_log = 2
        while futures:
            completed, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed:
                ticker = futures[future]
                del futures[future]
                completed_tickers += 1
                submit_next_ticker()
                try:
                    success, dcf_inputs, yahoo_profile, yahoo_overview, failure_reason = future.result()
                except Exception as e:
                    failure_reason = _log_ticker_exception("DCF worker", ticker, e)
                    failure_counts[failure_reason] += 1
                    continue
                if dcf_inputs:
                    forecast_error = dcf_inputs["extras"]["forecast_context"]["marketscreener_forecast_error"]
                    if forecast_error:
                        category = next(
                            (
                                marker
                                for marker in (
                                    "MarketScreener has no analyst forecast page",
                                    "MarketScreener redirected forecast request",
                                    "MarketScreener forecast page missing income statement section",
                                    "MarketScreener anti-bot page returned",
                                )
                                if marker in forecast_error
                            ),
                            forecast_error.split(":", 1)[0],
                        )
                        marketscreener_forecast_failures[category] += 1
                        samples = marketscreener_forecast_failure_samples.setdefault(category, [])
                        if len(samples) < 5:
                            samples.append(ticker)
                    else:
                        dcf_records.append((ticker, dcf_inputs))
                if yahoo_profile:
                    yahoo_profiles[yahoo_profile["Ticker"]] = yahoo_profile
                if yahoo_overview:
                    yahoo_overviews[yahoo_overview["Ticker"]] = yahoo_overview
                if not success:
                    if failure_reason.startswith("skipped:"):
                        skipped_counts[failure_reason] += 1
                    else:
                        failure_counts[failure_reason] += 1
                    continue

            while next_batch_to_log <= total_batches and completed_tickers >= (next_batch_to_log - 1) * DCF_MAX_WORKERS:
                _log_dcf_progress(next_batch_to_log, total_batches, completed_tickers, len(tickers), processing_started)
                if next_batch_to_log % 25 == 0:
                    log_marketscreener_stats()
                next_batch_to_log += 1

    num_errors = sum(failure_counts.values())
    logger.info("DCF scrape completed: %s errors out of %s tickers", num_errors, len(tickers))
    if skipped_counts:
        logger.info("DCF skipped summary: %s", ", ".join(f"{reason}: {count}" for reason, count in sorted(skipped_counts.items())))
    if failure_counts:
        logger.warning("DCF failure summary: %s", ", ".join(f"{reason}: {count}" for reason, count in sorted(failure_counts.items())))
    if marketscreener_forecast_failures:
        logger.warning(
            "MarketScreener forecast failures: %s tickers skipped from DCF DB update (%s)",
            sum(marketscreener_forecast_failures.values()),
            ", ".join(f"{reason}: {count}" for reason, count in sorted(marketscreener_forecast_failures.items())),
        )
        logger.warning(
            "MarketScreener forecast failure samples: %s",
            "; ".join(
                f"{reason}: {', '.join(tickers)}"
                for reason, tickers in sorted(marketscreener_forecast_failure_samples.items())
            ),
        )

    dcf_operations = [UpdateOne({"Ticker": ticker}, {"$set": record}, upsert=True) for ticker, record in dcf_records]
    if dcf_operations:
        dcf_db.bulk_write(dcf_operations, ordered=False)

    macro_db = client[db_name]["macro"]
    macro_db.update_one(
        filter={},
        update={
            "$set": {
                "Macro": {
                    "Country ERPs": country_erps,
                    "Avg Metrics": avg_metrics,
                    "Risk Free Rate": risk_free_rate,
                    "Mature ERP": mature_erp,
                }
            }
        },
        upsert=True,
    )
    overview_records = normalize_json(list(yahoo_overviews.values()))
    overview_operations = [UpdateOne({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True) for record in overview_records]
    if overview_operations:
        overview_db.bulk_write(overview_operations, ordered=False)
    logger.info("Yahoo overviews saved: %s out of %s tickers", len(overview_records), len(tickers))

    return yahoo_profiles


def run_market_discovery_scrape(tickers, client, yahoo_snapshots=None, include_sector_industries=True):
    db_name = os.getenv("MONGODB_DB_NAME")
    similar_db = client[db_name]["similar_companies"]
    industries_db = client[db_name]["industries"]

    yahoo_snapshots = yahoo_snapshots or {}
    logger.info("Running similar companies scrape for %s tickers", len(tickers))
    similar_failures = 0
    similar_records = []
    for ticker in tickers:
        try:
            snapshot = yahoo_snapshots.get(ticker)
            record = get_similar_companies(ticker, yahoo_info=snapshot.get_info() if snapshot else None)
            if record:
                similar_records.append(normalize_json(record))
        except Exception as e:
            similar_failures += 1
            _log_ticker_exception("Similar companies scrape", ticker, e)
    similar_operations = [
        UpdateOne({"Ticker": record["Ticker"]}, {"$set": record, "$unset": {"similar_companies": ""}}, upsert=True)
        for record in similar_records
    ]
    if similar_operations:
        similar_db.bulk_write(similar_operations, ordered=False)
    if similar_failures:
        logger.warning("Similar companies scrape failures: %s", similar_failures)

    if not include_sector_industries:
        logger.info("Skipping sector industry scrape for this ticker chunk")
        return

    logger.info("Running sector industry scrape")
    industries = get_sector_industries()
    industry_records = normalize_json(industries)
    industry_operations = [UpdateOne({"industry_key": record["industry_key"]}, {"$set": record}, upsert=True) for record in industry_records]
    if industry_operations:
        industries_db.bulk_write(industry_operations, ordered=False)
    logger.info("Industry records saved: %s", len(industry_records))


def run_comps_scrape(tickers, client, cached_yahoo_profiles=None, yahoo_snapshots=None, sec_ttm_future=None):
    yahoo_df = get_and_parse_yahoo(tickers, cached_profiles=cached_yahoo_profiles, yahoo_snapshots=yahoo_snapshots)
    fx_rates = get_exchange_rates()
    sec_financials_by_ticker = None
    if sec_ttm_future is not None:
        wait_started = time.monotonic()
        try:
            sec_financials_by_ticker = sec_ttm_future.result()
        except Exception as e:
            logger.warning("SEC TTM prefetch failed; continuing comps with Yahoo financials only: %s", e)
            logger.debug("SEC TTM prefetch failed\n%s", traceback.format_exc())
            sec_financials_by_ticker = {ticker: {"Ticker": ticker} for ticker in tickers}
        logger.info("SEC TTM prefetch wait during comps: %.1fs", time.monotonic() - wait_started)
    ttm_financials_df = compute_ttm_financials(
        tickers,
        yahoo_snapshots=yahoo_snapshots,
        fx_rates=fx_rates,
        sec_financials_by_ticker=sec_financials_by_ticker,
    )

    db = client[os.getenv("MONGODB_DB_NAME")]["financials"]
    operations = []
    for df in [yahoo_df, ttm_financials_df]:
        if df.empty:
            continue
        records = df.astype(object).where(pd.notna(df), None).reset_index(names="Ticker")
        records = normalize_json(records.to_dict(orient="records"))
        operations.extend(
            UpdateOne(
                {"Ticker": record["Ticker"]},
                {"$set": {key: value for key, value in record.items() if value is not None}},
                upsert=True,
            )
            for record in records
        )
    if operations:
        db.bulk_write(operations, ordered=False)


def main():
    started = time.monotonic()
    all_tickers = get_all_tickers()
    logger.info("Tickers loaded: %s", len(all_tickers))
    tickers = _get_ticker_chunk(all_tickers)
    client = get_mongo_client()
    load_marketscreener_cache()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as sec_executor:
            sec_cancel_event = threading.Event()
            logger.info("Starting SEC TTM prefetch for %s tickers", len(tickers))
            sec_ttm_future = sec_executor.submit(prefetch_sec_ttm_financials, tickers, sec_cancel_event)
            try:
                yahoo_snapshots = _log_timing("Yahoo snapshot scrape", get_yahoo_snapshots, tickers)
                yahoo_profiles = _log_timing("DCF scrape", run_dcf_scrape, tickers, client, yahoo_snapshots)
                logger.info("Running comps scrape")
                _log_timing("Comps scrape", run_comps_scrape, tickers, client, yahoo_profiles, yahoo_snapshots, sec_ttm_future)
            finally:
                sec_cancel_event.set()
        include_sector_industries = os.getenv("RUN_SECTOR_INDUSTRY_SCRAPE", "1") != "0"
        _log_timing(
            "Market discovery scrape",
            run_market_discovery_scrape,
            tickers,
            client,
            yahoo_snapshots,
            include_sector_industries,
        )
    finally:
        log_marketscreener_stats()
        save_marketscreener_cache()
        logger.info("Full scrape completed in %.1fs", time.monotonic() - started)


def process_ticker(ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, fx_rates, yahoo_snapshot=None, marketscreener_executor=None):
    try:
        dcf_result = run_with_timeout(
            get_dcf_inputs,
            TICKER_TIMEOUT_SECONDS,
            ticker,
            country_erps,
            region_mapper,
            avg_metrics,
            industry_mapper,
            mature_erp,
            risk_free_rate,
            fx_rates,
            yahoo_snapshot,
            marketscreener_executor,
            cancel_event_kwarg="cancel_event",
        )
        dcf_inputs = normalize_json(dcf_result["dcf_inputs"])
        return True, dcf_inputs, dcf_result.get("yahoo_profile"), dcf_result.get("yahoo_overview"), None
    except TimeoutError:
        logger.warning("DCF scrape timed out for %s", ticker)
        return False, None, None, None, "timeout"
    except MissingFinancialStatements:
        logger.warning("DCF scrape skipped for %s: missing financial statements", ticker)
        return False, None, None, None, "skipped:missing_financial_statements"
    except Exception as e:
        failure_reason = _log_ticker_exception("DCF scrape", ticker, e)
        return False, None, None, None, failure_reason


if __name__ == "__main__":
    main()
