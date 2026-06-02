import logging
import time
from datetime import date
from functools import lru_cache

import requests

from scrape.core.config import REQUEST_TIMEOUT_SECONDS, SEC_USER_AGENT
from scrape.core.policies import SEC
from scrape.core.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

SEC_HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

FACT_SPECS = {
    "Revenue": {
        "preferred": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "include_any": [("revenue",), ("sales",)],
        "exclude_any": [
            "cost",
            "expense",
            "deferred",
            "unearned",
            "contract liability",
            "remaining performance",
            "tax",
            "interest income",
            "noninterest income",
            "investment income",
            "other income",
            "gain",
            "per share",
            "securities",
            "proceeds",
            "commission",
            "pro forma",
        ],
    },
    "Net Income": {
        "preferred": ["NetIncomeLoss", "ProfitLoss"],
        "include_any": [("net", "income"), ("profit", "loss")],
        "exclude_any": ["per share", "available to common", "attributable", "comprehensive", "before", "tax"],
    },
    "EBIT": {
        "preferred": [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ],
        "include_any": [("operating", "income"), ("income", "before", "tax")],
        "exclude_any": ["per share", "comprehensive", "nonoperating", "interest income"],
    },
    "EBITDA": {
        "preferred": [
            "EarningsBeforeInterestTaxesDepreciationAndAmortization",
            "IncomeLossFromContinuingOperationsBeforeInterestExpenseInterestIncomeIncomeTaxesExtraordinaryItemsNoncontrollingInterestsNetOfTaxDepreciationDepletionAndAmortization",
        ],
        "include_any": [("ebitda",), ("earnings", "before", "interest", "tax", "depreciation")],
        "exclude_any": ["adjusted", "margin", "per share"],
    },
    "Depreciation & Amortization": {
        "preferred": [
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
        ],
        "include_any": [("depreciation", "amortization"), ("depreciation", "depletion", "amortization")],
        "exclude_any": ["accumulated", "assets", "property plant", "schedule", "policy", "useful life", "exploration"],
    },
}

MAX_FACT_AGE_DAYS = 540
_sec_limiter = RateLimiter(SEC.rate_limit.min_interval_seconds, SEC.rate_limit.jitter_seconds)
_sec_session = requests.Session()


class SecRateLimited(RuntimeError):
    pass


def days_between(start, end):
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


def _sec_get_json(url):
    for attempt in range(SEC.retry.attempts):
        _sec_limiter.wait()
        response = _sec_session.get(url, headers=SEC_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()

        if attempt == SEC.retry.attempts - 1:
            raise SecRateLimited(f"SEC 429 after {SEC.retry.attempts} attempts for {response.url}")

        retry_after = response.headers.get("Retry-After")
        try:
            sleep_seconds = float(retry_after) if retry_after else SEC.retry.backoff(attempt)
        except ValueError:
            sleep_seconds = SEC.retry.backoff(attempt)
        logger.info("SEC rate limited; retrying in %.1fs", sleep_seconds)
        time.sleep(sleep_seconds)


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


def quarterly_values(companyfacts, spec):
    candidates = []
    preferred_tags = set(spec["preferred"])
    for taxonomy, facts_by_tag in companyfacts.get("facts", {}).items():
        if taxonomy == "dei":
            continue
        for tag, fact_definition in facts_by_tag.items():
            if tag not in preferred_tags:
                text = " ".join(
                    str(value)
                    for value in [tag, fact_definition.get("label"), fact_definition.get("description")]
                    if value
                ).lower()
                if any(excluded in text for excluded in spec["exclude_any"]):
                    continue
                if not any(all(term in text for term in terms) for terms in spec["include_any"]):
                    continue

            quarters = quarterly_values_for_facts(fact_definition.get("units", {}).get("USD") or [])
            if not quarters:
                continue
            age_days = days_between(quarters[0].get("end"), date.today().isoformat())
            if age_days is not None and age_days <= MAX_FACT_AGE_DAYS:
                candidates.append((tag, quarters))

    candidates = [candidate for candidate in candidates if candidate[0] in preferred_tags] or candidates
    if not candidates:
        return []
    return max(candidates, key=lambda candidate: (candidate[1][0]["end"], len(candidate[1])))[1]


def latest_and_previous_ttm(companyfacts, spec):
    quarters = quarterly_values(companyfacts, spec)
    latest = sum(q["val"] for q in quarters[:4]) if len(quarters) >= 4 else None
    previous = sum(q["val"] for q in quarters[4:8]) if len(quarters) >= 8 else None
    return latest, previous, quarters


def get_sec_ttm_financials(ticker):
    cik = get_cik_for_ticker(ticker)
    if cik is None:
        return {"Ticker": ticker}

    companyfacts = get_companyfacts(cik)
    revenue_ttm, revenue_prev_ttm, revenue_quarters = latest_and_previous_ttm(companyfacts, FACT_SPECS["Revenue"])
    result = {
        "Ticker": ticker,
        "Revenue TTM": revenue_ttm,
        "Revenue Prev TTM": revenue_prev_ttm,
        "TTM Period End": revenue_quarters[0]["end"] if revenue_quarters else None,
    }

    for prefix in ["Net Income", "EBIT"]:
        latest, previous, _ = latest_and_previous_ttm(companyfacts, FACT_SPECS[prefix])
        result[f"{prefix} TTM"] = latest
        result[f"{prefix} Prev TTM"] = previous

    ebitda_ttm, ebitda_prev_ttm, _ = latest_and_previous_ttm(companyfacts, FACT_SPECS["EBITDA"])
    depreciation_ttm, depreciation_prev_ttm, _ = latest_and_previous_ttm(
        companyfacts, FACT_SPECS["Depreciation & Amortization"]
    )
    result["EBITDA TTM"] = ebitda_ttm
    if result["EBITDA TTM"] is None and result["EBIT TTM"] is not None and depreciation_ttm is not None:
        result["EBITDA TTM"] = result["EBIT TTM"] + depreciation_ttm

    result["EBITDA Prev TTM"] = ebitda_prev_ttm
    if result["EBITDA Prev TTM"] is None and result["EBIT Prev TTM"] is not None and depreciation_prev_ttm is not None:
        result["EBITDA Prev TTM"] = result["EBIT Prev TTM"] + depreciation_prev_ttm

    return result
