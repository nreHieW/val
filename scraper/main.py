import concurrent.futures
import json
import logging
import os
import time
import traceback

import pandas as pd
from pymongo import UpdateOne

from scrape.core.config import DCF_MAX_WORKERS, MARKETSCREENER_MAX_WORKERS, TICKER_TIMEOUT_SECONDS
from scrape.core.http_utils import run_with_timeout
from scrape.core.json_util import CustomEncoder
from scrape.core.mongo import get_mongo_client
from scrape.core.tickers import get_all_tickers
from scrape.sources.marketscreener import load_marketscreener_cache, save_marketscreener_cache
from scrape.sources.yahoo_market_discovery import get_sector_industries, get_similar_companies
from scrape.sources.yahoo_profiles import compute_ttm_financials, get_and_parse_yahoo
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


def marketscreener_forecast_failed(record):
    return bool(
        ((record.get("extras") or {}).get("forecast_context") or {}).get(
            "marketscreener_forecast_error"
        )
    )


def run_dcf_scrape(tickers, client, yahoo_snapshots=None):
    yahoo_snapshots = yahoo_snapshots or {}
    logger.info(f"Running DCF scrape for {len(tickers)} tickers")
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
    failure_counts = {}
    skipped_counts = {}
    yahoo_profiles = {}
    yahoo_overviews = {}
    dcf_records = []
    marketscreener_forecast_failures = 0

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
            logger.info("Processing batch 1 of %s", total_batches)

        completed_tickers = 0
        next_batch_to_log = 2
        while futures:
            completed, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed:
                ticker = futures[future]
                success, dcf_inputs, yahoo_profile, yahoo_overview, failure_reason = future.result()
                del futures[future]
                completed_tickers += 1
                submit_next_ticker()
                if dcf_inputs:
                    if marketscreener_forecast_failed(dcf_inputs):
                        marketscreener_forecast_failures += 1
                    else:
                        dcf_records.append((ticker, dcf_inputs))
                if yahoo_profile:
                    yahoo_profiles[yahoo_profile["Ticker"]] = yahoo_profile
                if yahoo_overview:
                    yahoo_overviews[yahoo_overview["Ticker"]] = yahoo_overview
                if not success:
                    if failure_reason and failure_reason.startswith("skipped:"):
                        skipped_counts[failure_reason] = skipped_counts.get(failure_reason, 0) + 1
                    else:
                        failure_counts[failure_reason] = failure_counts.get(failure_reason, 0) + 1
                    continue

            while next_batch_to_log <= total_batches and completed_tickers >= (next_batch_to_log - 1) * DCF_MAX_WORKERS:
                logger.info("Processing batch %s of %s", next_batch_to_log, total_batches)
                next_batch_to_log += 1

    num_errors = sum(failure_counts.values())
    logger.info("DCF scrape completed: %s errors out of %s tickers", num_errors, len(tickers))
    if skipped_counts:
        logger.info("DCF skipped summary: %s", ", ".join(f"{reason}: {count}" for reason, count in sorted(skipped_counts.items())))
    if failure_counts:
        logger.warning("DCF failure summary: %s", ", ".join(f"{reason}: {count}" for reason, count in sorted(failure_counts.items())))
    if marketscreener_forecast_failures:
        logger.warning(
            "MarketScreener forecast failures: %s tickers skipped from DCF DB update",
            marketscreener_forecast_failures,
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
    overview_records = json.loads(json.dumps(list(yahoo_overviews.values()), cls=CustomEncoder))
    overview_operations = [UpdateOne({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True) for record in overview_records]
    if overview_operations:
        overview_db.bulk_write(overview_operations, ordered=False)
    logger.info("Yahoo overviews saved: %s out of %s tickers", len(overview_records), len(tickers))

    return yahoo_profiles


def run_market_discovery_scrape(tickers, client, yahoo_snapshots=None):
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
            record = get_similar_companies(ticker, yahoo_info=snapshot.info if snapshot else None)
            if record:
                similar_records.append(json.loads(json.dumps(record, cls=CustomEncoder)))
        except Exception:
            similar_failures += 1
            logger.debug("Similar companies scrape failed for %s\n%s", ticker, traceback.format_exc())
    similar_operations = [
        UpdateOne({"Ticker": record["Ticker"]}, {"$set": record, "$unset": {"similar_companies": ""}}, upsert=True)
        for record in similar_records
    ]
    if similar_operations:
        similar_db.bulk_write(similar_operations, ordered=False)
    if similar_failures:
        logger.warning("Similar companies scrape failures: %s", similar_failures)

    logger.info("Running sector industry scrape")
    industries = get_sector_industries()
    industry_records = json.loads(json.dumps(industries, cls=CustomEncoder))
    industry_operations = [UpdateOne({"industry_key": record["industry_key"]}, {"$set": record}, upsert=True) for record in industry_records]
    if industry_operations:
        industries_db.bulk_write(industry_operations, ordered=False)
    logger.info("Industry records saved: %s", len(industry_records))


def run_comps_scrape(tickers, client, cached_yahoo_profiles=None, yahoo_snapshots=None):
    yahoo_df = get_and_parse_yahoo(tickers, cached_profiles=cached_yahoo_profiles, yahoo_snapshots=yahoo_snapshots)
    fx_rates = get_exchange_rates()
    ttm_financials_df = compute_ttm_financials(tickers, yahoo_snapshots=yahoo_snapshots, fx_rates=fx_rates)

    db = client[os.getenv("MONGODB_DB_NAME")]["financials"]
    operations = []
    for df in [yahoo_df, ttm_financials_df]:
        if df.empty:
            continue
        records = df.astype(object).where(pd.notna(df), None).reset_index()
        records = records.rename(columns={"index": "Ticker"})
        records = json.loads(json.dumps(records.to_dict(orient="records"), cls=CustomEncoder))
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
    tickers = get_all_tickers()
    logger.info("Tickers loaded: %s", len(tickers))
    client = get_mongo_client()
    load_marketscreener_cache()
    try:
        yahoo_snapshots = _log_timing("Yahoo snapshot scrape", get_yahoo_snapshots, tickers)
        yahoo_profiles = _log_timing("DCF scrape", run_dcf_scrape, tickers, client, yahoo_snapshots)
        logger.info("Running comps scrape")
        _log_timing("Comps scrape", run_comps_scrape, tickers, client, yahoo_profiles, yahoo_snapshots)
        _log_timing("Market discovery scrape", run_market_discovery_scrape, tickers, client, yahoo_snapshots)
    finally:
        save_marketscreener_cache()
        logger.info("Full scrape completed in %.1fs", time.monotonic() - started)


def _exception_location(exc: Exception) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    if not tb:
        return type(exc).__name__
    frame = tb[-1]
    return f"{type(exc).__name__} at {os.path.relpath(frame.filename)}:{frame.lineno} in {frame.name}"


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
        )
        dcf_inputs = json.dumps(dcf_result["dcf_inputs"], cls=CustomEncoder)
        dcf_inputs = json.loads(dcf_inputs)
        return True, dcf_inputs, dcf_result.get("yahoo_profile"), dcf_result.get("yahoo_overview"), None
    except TimeoutError:
        return False, None, None, None, "timeout"
    except MissingFinancialStatements:
        logger.warning("DCF scrape skipped for %s: missing financial statements", ticker)
        return False, None, None, None, "skipped:missing_financial_statements"
    except Exception as e:
        failure_reason = _exception_location(e)
        logger.warning("DCF scrape failed for %s: %s", ticker, failure_reason)
        logger.debug("DCF scrape failed for %s\n%s", ticker, "".join(traceback.format_exception(type(e), e, e.__traceback__)))
        return False, None, None, None, failure_reason


if __name__ == "__main__":
    main()
