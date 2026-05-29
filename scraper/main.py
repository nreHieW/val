import concurrent.futures
import json
import logging
import os
import time
import traceback
import pandas as pd
from pymongo import UpdateOne
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import MAX_WORKERS, TICKER_TIMEOUT_SECONDS
from scrape.core.http_utils import run_with_timeout
from scrape.core.json_util import CustomEncoder
from scrape.core.mongo import get_mongo_client
from scrape.core.tickers import get_all_tickers
from scrape.sources.finviz import parse_finviz
from scrape.sources.yahoo_market_discovery import get_sector_industries, get_similar_companies
from scrape.sources.yahoo_overview import build_yahoo_overview
from scrape.sources.yahoo_profiles import compute_ttm_financials, get_and_parse_yahoo
from scrape.sources.yahoo_snapshot import get_yahoo_snapshots
from scrape.valuation.dcf_inputs import get_dcf_inputs
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


def run_dcf_scrape(tickers, client, yahoo_snapshots=None):
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
    yahoo_snapshots = yahoo_snapshots or {}
    yahoo_profiles = {}
    yahoo_overviews = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(0, len(tickers), MAX_WORKERS):
            logger.info(f"Processing batch {i // MAX_WORKERS + 1} of {len(tickers) // MAX_WORKERS + 1}")
            batch = tickers[i : i + MAX_WORKERS]
            futures = [
                executor.submit(process_ticker, ticker, yahoo_snapshots.get(ticker), country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, dcf_db, fx_rates)
                for ticker in batch
            ]

            for future in concurrent.futures.as_completed(futures):
                success, yahoo_profile, yahoo_overview, failure_reason = future.result()
                if yahoo_profile:
                    yahoo_profiles[yahoo_profile["Ticker"]] = yahoo_profile
                if yahoo_overview:
                    yahoo_overviews[yahoo_overview["Ticker"]] = yahoo_overview
                if not success:
                    failure_counts[failure_reason] = failure_counts.get(failure_reason, 0) + 1
                    continue

            if i + MAX_WORKERS < len(tickers):
                time.sleep(1)

    num_errors = sum(failure_counts.values())
    logger.info("DCF scrape completed: %s errors out of %s tickers", num_errors, len(tickers))
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
    for ticker, snapshot in yahoo_snapshots.items():
        if ticker not in yahoo_profiles:
            continue
        try:
            overview = build_yahoo_overview(snapshot.yf_ticker, snapshot.info)
            if overview:
                yahoo_overviews[overview["Ticker"]] = overview
        except Exception as e:
            logger.debug("Yahoo overview skipped for %s: %s", ticker, e)

    overview_records = json.loads(json.dumps(list(yahoo_overviews.values()), cls=CustomEncoder))
    if overview_records:
        overview_db.bulk_write(
            [UpdateOne({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True) for record in overview_records]
        )
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
    if industry_records:
        industries_db.bulk_write(
            [UpdateOne({"industry_key": record["industry_key"]}, {"$set": record}, upsert=True) for record in industry_records]
        )
    logger.info("Industry records saved: %s", len(industry_records))


def run_comps_scrape(tickers, client, cached_yahoo_profiles=None, yahoo_snapshots=None):
    yahoo_df = get_and_parse_yahoo(tickers, cached_profiles=cached_yahoo_profiles, yahoo_snapshots=yahoo_snapshots)
    ttm_financials_df = compute_ttm_financials(tickers, yahoo_snapshots=yahoo_snapshots)
    finviz_df = parse_finviz(tickers)

    combined = pd.concat([yahoo_df, ttm_financials_df, finviz_df], axis=1, join="outer")
    combined = combined.astype(object).where(pd.notna(combined), None)
    combined.reset_index(inplace=True)
    combined = combined.rename(columns={"index": "Ticker"})
    combined.sort_values("Ticker", inplace=True)

    db = client[os.getenv("MONGODB_DB_NAME")]["financials"]
    data = combined.to_dict(orient="records")
    data = json.loads(json.dumps(data, cls=CustomEncoder))
    if data:
        db.bulk_write(
            [UpdateOne({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True) for record in data]
        )


def main():
    tickers = get_all_tickers()[:1000]
    logger.info("Tickers loaded: %s", len(tickers))
    client = get_mongo_client()
    yahoo_snapshots = get_yahoo_snapshots(tickers)
    yahoo_profiles = run_dcf_scrape(tickers, client, yahoo_snapshots=yahoo_snapshots)
    logger.info("Running comps scrape")
    run_comps_scrape(tickers, client, cached_yahoo_profiles=yahoo_profiles, yahoo_snapshots=yahoo_snapshots)
    run_market_discovery_scrape(tickers, client)


def _exception_location(exc: Exception) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    if not tb:
        return type(exc).__name__
    frame = tb[-1]
    return f"{type(exc).__name__} at {os.path.relpath(frame.filename)}:{frame.lineno} in {frame.name}"


def process_ticker(ticker, yahoo_snapshot, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, db, fx_rates):
    if yahoo_snapshot is None:
        return False, None, None, "missing_yahoo_snapshot"
    try:
        dcf_result = run_with_timeout(
            get_dcf_inputs,
            TICKER_TIMEOUT_SECONDS,
            yahoo_snapshot,
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
    except Exception as e:
        failure_reason = _exception_location(e)
        logger.debug("DCF scrape failed for %s\n%s", ticker, "".join(traceback.format_exception(type(e), e, e.__traceback__)))
        return False, None, None, failure_reason


if __name__ == "__main__":
    main()
