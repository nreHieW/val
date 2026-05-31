import logging
from datetime import date
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

SEC_HEADERS = {"User-Agent": "Val financial scraper contact@example.com"}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]
EBIT_TAGS = ["OperatingIncomeLoss", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"]


def days_between(start, end):
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def get_sec_ticker_cik_map():
    response = requests.get(TICKER_MAP_URL, headers=SEC_HEADERS, timeout=30)
    response.raise_for_status()
    return {
        item["ticker"].upper(): int(item["cik_str"])
        for item in response.json().values()
        if item.get("ticker") and item.get("cik_str")
    }


def get_cik_for_ticker(ticker):
    return get_sec_ticker_cik_map().get(ticker.upper().replace(".", "-"))


@lru_cache(maxsize=10000)
def get_companyfacts(cik):
    response = requests.get(COMPANYFACTS_URL.format(cik=cik), headers=SEC_HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def quarterly_values_for_facts(facts):
    quarters_by_end = {}
    for fact in facts:
        days = days_between(fact.get("start"), fact.get("end"))
        if fact.get("form") == "10-Q" and days is not None and 70 <= days <= 110:
            end = fact.get("end")
            previous = quarters_by_end.get(end)
            if end and (previous is None or str(fact.get("filed", "")) > str(previous.get("filed", ""))):
                quarters_by_end[end] = fact

    quarters = [
        {
            "start": fact.get("start"),
            "end": fact.get("end"),
            "val": float(fact["val"]),
        }
        for fact in quarters_by_end.values()
        if fact.get("val") is not None
    ]

    for annual in facts:
        days = days_between(annual.get("start"), annual.get("end"))
        if annual.get("form") != "10-K" or annual.get("fp") != "FY" or days is None or not 330 <= days <= 380 or annual.get("val") is None:
            continue
        if any(q["end"] == annual.get("end") for q in quarters):
            continue
        fiscal_quarters = [
            q
            for q in quarters
            if q.get("start") and annual["start"] <= q["start"] and q["end"] < annual["end"]
        ]
        if len(fiscal_quarters) == 3:
            quarters.append(
                {
                    "start": None,
                    "end": annual["end"],
                    "val": float(annual["val"]) - sum(q["val"] for q in fiscal_quarters),
                }
            )

    return sorted(quarters, key=lambda q: q["end"], reverse=True)


def quarterly_values(companyfacts, tags):
    candidates = []
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        units = us_gaap.get(tag, {}).get("units", {})
        facts = units.get("USD") or []
        quarters = quarterly_values_for_facts(facts)
        if quarters:
            candidates.append(quarters)
    return max(candidates, key=lambda qs: (qs[0]["end"], len(qs))) if candidates else []


def latest_and_previous_ttm(companyfacts, tags):
    quarters = quarterly_values(companyfacts, tags)
    if len(quarters) < 8:
        return None, None, quarters
    return sum(q["val"] for q in quarters[:4]), sum(q["val"] for q in quarters[4:8]), quarters


def get_sec_ttm_financials(ticker):
    cik = get_cik_for_ticker(ticker)
    if cik is None:
        raise RuntimeError(f"SEC CIK unavailable for {ticker}")

    companyfacts = get_companyfacts(cik)
    revenue_ttm, revenue_prev_ttm, revenue_quarters = latest_and_previous_ttm(companyfacts, REVENUE_TAGS)
    if revenue_ttm is None or revenue_prev_ttm is None:
        raise RuntimeError(f"SEC revenue TTM unavailable for {ticker}; quarters={len(revenue_quarters)}")

    result = {
        "Ticker": ticker,
        "Revenue TTM": revenue_ttm,
        "Revenue Prev TTM": revenue_prev_ttm,
        "TTM Period End": revenue_quarters[0]["end"],
    }

    for prefix, tags in [("Net Income", NET_INCOME_TAGS), ("EBIT", EBIT_TAGS)]:
        latest, previous, quarters = latest_and_previous_ttm(companyfacts, tags)
        if latest is None or previous is None:
            logger.warning("SEC %s TTM unavailable for %s; quarters=%s", prefix, ticker, len(quarters))
        result[f"{prefix} TTM"] = latest
        result[f"{prefix} Prev TTM"] = previous

    return result
