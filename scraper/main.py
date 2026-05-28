import concurrent.futures
import json
import logging
import os
import time
import traceback
import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import MAX_WORKERS, TICKER_TIMEOUT_SECONDS
from scrape.core.http_utils import run_with_timeout
from scrape.core.json_util import CustomEncoder
from scrape.core.mongo import get_mongo_client
from scrape.core.tickers import get_all_tickers
from scrape.sources.finviz import parse_finviz
from scrape.sources.yahoo_market_discovery import get_sector_industries, get_similar_companies
from scrape.sources.yahoo_overview import build_yahoo_overview
from scrape.sources.yahoo_profiles import build_yahoo_profile, compute_ttm_financials, get_and_parse_yahoo
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
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)


def run_dcf_scrape(tickers, client):
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

    consecutive_rate_limited_batches = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, len(tickers), MAX_WORKERS):
            logger.info(f"Processing batch {i // MAX_WORKERS + 1} of {len(tickers) // MAX_WORKERS + 1}")
            batch = tickers[i : i + MAX_WORKERS]
            futures = [
                executor.submit(process_ticker, ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, dcf_db, fx_rates)
                for ticker in batch
            ]
            batch_failure_counts = {}

            for future in concurrent.futures.as_completed(futures):
                success, yahoo_profile, yahoo_overview, failure_reason = future.result()
                if yahoo_profile:
                    yahoo_profiles[yahoo_profile["Ticker"]] = yahoo_profile
                if yahoo_overview:
                    yahoo_overviews[yahoo_overview["Ticker"]] = yahoo_overview
                if not success:
                    if failure_reason and failure_reason.startswith("skipped:"):
                        skipped_counts[failure_reason] = skipped_counts.get(failure_reason, 0) + 1
                    else:
                        failure_counts[failure_reason] = failure_counts.get(failure_reason, 0) + 1
                        batch_failure_counts[failure_reason] = batch_failure_counts.get(failure_reason, 0) + 1
                    continue

            if batch_failure_counts.get("yahoo_rate_limit") == len(batch):
                consecutive_rate_limited_batches += 1
                if consecutive_rate_limited_batches >= 3:
                    remaining = len(tickers) - i - len(batch)
                    if remaining > 0:
                        failure_counts["skipped_after_rate_limit"] = remaining
                    logger.warning("Stopping DCF scrape early after repeated Yahoo rate-limited batches")
                    break
            else:
                consecutive_rate_limited_batches = 0

            if i + MAX_WORKERS < len(tickers):
                time.sleep(1)

    num_errors = sum(failure_counts.values())
    logger.info("DCF scrape completed: %s errors out of %s tickers", num_errors, len(tickers))
    if skipped_counts:
        logger.info("DCF skipped summary: %s", ", ".join(f"{reason}: {count}" for reason, count in sorted(skipped_counts.items())))
    if failure_counts:
        logger.warning("DCF failure summary: %s", ", ".join(f"{reason}: {count}" for reason, count in sorted(failure_counts.items())))

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
    for record in overview_records:
        overview_db.update_one({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True)
    logger.info("Yahoo overviews saved: %s out of %s tickers", len(overview_records), len(tickers))

    return yahoo_profiles


def run_market_discovery_scrape(tickers, client):
    db_name = os.getenv("MONGODB_DB_NAME")
    similar_db = client[db_name]["similar_companies"]
    industries_db = client[db_name]["industries"]

    logger.info("Running similar companies scrape for %s tickers", len(tickers))
    similar_failures = 0
    for ticker in tickers:
        try:
            record = get_similar_companies(ticker)
            if record:
                record = json.loads(json.dumps(record, cls=CustomEncoder))
                similar_db.update_one(
                    {"Ticker": record["Ticker"]},
                    {"$set": record, "$unset": {"similar_companies": ""}},
                    upsert=True,
                )
        except Exception:
            similar_failures += 1
            logger.debug("Similar companies scrape failed for %s\n%s", ticker, traceback.format_exc())
    if similar_failures:
        logger.warning("Similar companies scrape failures: %s", similar_failures)

    logger.info("Running sector industry scrape")
    industries = get_sector_industries()
    industry_records = json.loads(json.dumps(industries, cls=CustomEncoder))
    for record in industry_records:
        industries_db.update_one({"industry_key": record["industry_key"]}, {"$set": record}, upsert=True)
    logger.info("Industry records saved: %s", len(industry_records))


def run_comps_scrape(tickers, client, cached_yahoo_profiles=None):
    yahoo_df = get_and_parse_yahoo(tickers, cached_profiles=cached_yahoo_profiles)
    ttm_financials_df = compute_ttm_financials(tickers)
    finviz_df = parse_finviz(tickers)

    combined = pd.concat([yahoo_df, ttm_financials_df, finviz_df], axis=1, join="outer")
    combined = combined.astype(object).where(pd.notna(combined), None)
    combined.reset_index(inplace=True)
    combined = combined.rename(columns={"index": "Ticker"})
    combined.sort_values("Ticker", inplace=True)

    db = client[os.getenv("MONGODB_DB_NAME")]["financials"]
    data = combined.to_dict(orient="records")
    data = json.loads(json.dumps(data, cls=CustomEncoder))
    for record in data:
        # Yahoo occasionally rate-limits or returns partial profile data. Avoid
        # replacing previously good comparison fields with nulls; missing values
        # are simply left unchanged until the next successful scrape.
        cleaned_record = {key: value for key, value in record.items() if value is not None}
        db.update_one({"Ticker": record["Ticker"]}, {"$set": cleaned_record}, upsert=True)


def main():
    tickers = get_all_tickers()[:2000]
    logger.info("Tickers loaded: %s", len(tickers))
    client = get_mongo_client()
    yahoo_profiles = run_dcf_scrape(tickers, client)
    logger.info("Running comps scrape")
    run_comps_scrape(tickers, client, cached_yahoo_profiles=yahoo_profiles)
    run_market_discovery_scrape(tickers, client)


def _exception_location(exc: Exception) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    if not tb:
        return type(exc).__name__
    frame = tb[-1]
    return f"{type(exc).__name__} at {os.path.relpath(frame.filename)}:{frame.lineno} in {frame.name}"


def process_ticker(ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, db, fx_rates):
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
        )
        dcf_inputs = json.dumps(dcf_result["dcf_inputs"], cls=CustomEncoder)
        dcf_inputs = json.loads(dcf_inputs)
        db.update_one({"Ticker": ticker}, {"$set": dcf_inputs}, upsert=True)
        return True, dcf_result.get("yahoo_profile"), dcf_result.get("yahoo_overview"), None
    except TimeoutError:
        return False, None, None, "timeout"
    except YFRateLimitError:
        return False, None, None, "yahoo_rate_limit"
    except MissingFinancialStatements:
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.get_info()
            yahoo_profile = build_yahoo_profile(info.get("symbol", ticker), info)
            try:
                yahoo_overview = build_yahoo_overview(yf_ticker, info)
            except Exception:
                yahoo_overview = None
            return False, yahoo_profile, yahoo_overview, "skipped:missing_financial_statements"
        except Exception:
            logger.debug("Yahoo fallback failed for %s\n%s", ticker, traceback.format_exc())
            return False, None, None, "skipped:missing_financial_statements"
    except Exception as e:
        failure_reason = _exception_location(e)
        logger.debug("DCF scrape failed for %s\n%s", ticker, "".join(traceback.format_exception(type(e), e, e.__traceback__)))
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.get_info()
            yahoo_profile = build_yahoo_profile(info.get("symbol", ticker), info)
            try:
                yahoo_overview = build_yahoo_overview(yf_ticker, info)
            except Exception:
                yahoo_overview = None
            return False, yahoo_profile, yahoo_overview, failure_reason
        except Exception:
            logger.debug("Yahoo fallback failed for %s\n%s", ticker, traceback.format_exc())
            return False, None, None, failure_reason


if __name__ == "__main__":
    main()
