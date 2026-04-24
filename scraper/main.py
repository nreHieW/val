import concurrent.futures
import json
import os
import time

import pandas as pd

from scrape.core.config import MAX_WORKERS, TICKER_TIMEOUT_SECONDS
from scrape.core.http_utils import run_with_timeout
from scrape.core.json_util import CustomEncoder
from scrape.core.mongo import get_mongo_client
from scrape.core.tickers import get_all_tickers
from scrape.sources.finviz import parse_finviz
from scrape.sources.yahoo_profiles import compute_ttm_financials, get_and_parse_yahoo
from scrape.valuation.dcf_inputs import get_dcf_inputs
from scrape.valuation.market_metrics import (
    get_10year_tbill,
    get_country_erp,
    get_exchange_rates,
    get_industry_avgs,
    get_mature_erp,
)
from scrape.valuation.string_mapper import StringMapper


def run_dcf_scrape(tickers, client):
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
    yahoo_profiles = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for i, ticker in enumerate(tickers):
            if i > 0 and i % MAX_WORKERS == 0:
                time.sleep(1)
            future = executor.submit(process_ticker, ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, dcf_db, fx_rates)
            futures.append(future)

        for future in concurrent.futures.as_completed(futures):
            yahoo_profile = future.result()
            if yahoo_profile:
                yahoo_profiles[yahoo_profile["Ticker"]] = yahoo_profile

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
    return yahoo_profiles


def run_comps_scrape(tickers, client, cached_yahoo_profiles=None):
    yahoo_df = get_and_parse_yahoo(tickers, cached_profiles=cached_yahoo_profiles)
    ttm_financials_df = compute_ttm_financials(tickers)
    finviz_df = parse_finviz(tickers)

    combined = pd.concat([yahoo_df, ttm_financials_df, finviz_df], axis=1, join="outer")
    if "TTM Period End" in combined.columns:
        combined["TTM Period End"] = combined["TTM Period End"].replace(0, None)
    combined.reset_index(inplace=True)
    combined = combined.rename(columns={"index": "Ticker"})
    combined.sort_values("Ticker", inplace=True)

    db = client[os.getenv("MONGODB_DB_NAME")]["financials"]
    data = combined.to_dict(orient="records")
    data = json.loads(json.dumps(data, cls=CustomEncoder))
    for record in data:
        db.update_one({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True)


def main():
    tickers = get_all_tickers()
    print("Number of tickers:", len(tickers))
    client = get_mongo_client()
    yahoo_profiles = run_dcf_scrape(tickers, client)
    print("Running comps scrape")
    run_comps_scrape(tickers, client, cached_yahoo_profiles=yahoo_profiles)


def process_ticker(ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, db, fx_rates):
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
    return dcf_result.get("yahoo_profile")


if __name__ == "__main__":
    main()
