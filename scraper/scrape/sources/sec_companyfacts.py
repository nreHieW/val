import logging
import time
from datetime import date
from functools import lru_cache

import requests

from scrape.core.config import REQUEST_TIMEOUT_SECONDS, SEC_USER_AGENT
from scrape.core.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

SEC_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]
EBIT_TAGS = ["OperatingIncomeLoss", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"]

SEC_REQUEST_MIN_INTERVAL_SECONDS = 0.25
SEC_REQUEST_JITTER_SECONDS = 0.1
SEC_RETRIES = 4
SEC_RETRY_SLEEP_SECONDS = 30

_sec_limiter = RateLimiter(SEC_REQUEST_MIN_INTERVAL_SECONDS, SEC_REQUEST_JITTER_SECONDS)
_sec_session = requests.Session()


class SecRateLimited(RuntimeError):
    pass


def days_between(start, end):
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


def _sec_get_json(url):
    for attempt in range(SEC_RETRIES):
        _sec_limiter.wait()
        response = _sec_session.get(url, headers=SEC_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()

        if attempt == SEC_RETRIES - 1:
            raise SecRateLimited(f"SEC 429 after {SEC_RETRIES} attempts for {response.url}")

        retry_after = response.headers.get("Retry-After")
        try:
            sleep_seconds = float(retry_after) if retry_after else SEC_RETRY_SLEEP_SECONDS * (attempt + 1)
        except ValueError:
            sleep_seconds = SEC_RETRY_SLEEP_SECONDS * (attempt + 1)
        logger.debug("SEC rate limited; retrying in %.1fs", sleep_seconds)
        time.sleep(max(0.0, sleep_seconds))

    raise SecRateLimited(f"SEC 429 after {SEC_RETRIES} attempts for {url}")


@lru_cache(maxsize=1)
def get_sec_ticker_cik_map():
    return {
        item["ticker"].upper(): int(item["cik_str"])
        for item in _sec_get_json(TICKER_MAP_URL).values()
        if item.get("ticker") and item.get("cik_str")
    }


def get_cik_for_ticker(ticker):
    return get_sec_ticker_cik_map().get(ticker.upper().replace(".", "-"))


@lru_cache(maxsize=10000)
def get_companyfacts(cik):
    return _sec_get_json(COMPANYFACTS_URL.format(cik=cik))


def quarterly_values_for_facts(facts):
    quarters_by_end = {}
    for fact in facts:
        days = days_between(fact.get("start"), fact.get("end"))
        if fact.get("form") != "10-Q" or days is None or not 70 <= days <= 110:
            continue

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
        if annual.get("form") != "10-K" or annual.get("fp") != "FY" or days is None:
            continue
        if not 330 <= days <= 380 or annual.get("val") is None:
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
        facts = us_gaap.get(tag, {}).get("units", {}).get("USD") or []
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
            logger.debug("SEC %s TTM unavailable for %s; quarters=%s", prefix, ticker, len(quarters))
        result[f"{prefix} TTM"] = latest
        result[f"{prefix} Prev TTM"] = previous

    return result
