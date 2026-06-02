import concurrent.futures
import logging
import time
from functools import lru_cache

import pandas as pd

from scrape.core.config import YAHOO_INFO_MAX_WORKERS
from scrape.sources.sec_companyfacts import SecRateLimited, get_sec_ttm_financials
from scrape.sources.yahooquery_adapter import YahooQueryTicker

logger = logging.getLogger(__name__)

YAHOO_FINANCIAL_KEYS = [
    "Revenue TTM",
    "Revenue Prev TTM",
    "Net Income TTM",
    "Net Income Prev TTM",
    "EBIT TTM",
    "EBIT Prev TTM",
    "EBITDA TTM",
    "EBITDA Prev TTM",
    "Free Cash Flow TTM",
]
_TTM_METRIC_NAMES = {
    "Revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
    "Net Income": ["Net Income Common Stockholders", "Net Income Including Noncontrolling Interests", "Net Income"],
    "EBIT": ["EBIT", "Operating Income"],
}


def with_ttm_defaults(financials):
    result = dict(financials)
    for key in YAHOO_FINANCIAL_KEYS:
        result.setdefault(key, None)
    return result


def _batches(items):
    for start in range(0, len(items), YAHOO_INFO_MAX_WORKERS):
        yield items[start : start + YAHOO_INFO_MAX_WORKERS], start + YAHOO_INFO_MAX_WORKERS < len(items)


def _ticker_frame(records):
    if not records:
        return pd.DataFrame(index=pd.Index([], name="Ticker"))
    return pd.DataFrame(records).set_index("Ticker")


@lru_cache(maxsize=10000)
def get_yahoo_info(ticker):
    return YahooQueryTicker(ticker).get_info()


def build_yahoo_profile(ticker, ticker_info):
    return {
        "Ticker": ticker,
        "Name": ticker_info.get("longName"),
        "Market Cap": ticker_info.get("marketCap"),
        "Sector": ticker_info.get("sector"),
        "Summary": ticker_info.get("longBusinessSummary"),
        "Industry": ticker_info.get("industry"),
        "Shares Outstanding": ticker_info.get("sharesOutstanding"),
        "Institution Ownership": ticker_info.get("heldPercentInstitutions"),
        "Price": ticker_info.get("currentPrice"),
        "52-Week High": ticker_info.get("fiftyTwoWeekHigh"),
        "52-Week Low": ticker_info.get("fiftyTwoWeekLow"),
        "P/E": ticker_info.get("trailingPE"),
        "Forward PE": ticker_info.get("forwardPE"),
        "Price to Sales": ticker_info.get("priceToSalesTrailing12Months"),
        "Enterprise Value": ticker_info.get("enterpriseValue"),
        "Beta": ticker_info.get("beta"),
    }


def normalize_quarterly_statement(statement: pd.DataFrame) -> pd.DataFrame:
    if statement.empty:
        return pd.DataFrame()

    statement = statement.copy()
    statement = statement.loc[~statement.index.duplicated(keep="first")]
    ordered_columns = sorted(statement.columns, key=lambda column: pd.Timestamp(column), reverse=True)
    return statement.loc[:, ordered_columns].fillna(0)


def sum_statement_metric(statement: pd.DataFrame, metric_names: list[str], start=0, count=4):
    columns = list(statement.columns[start : start + count])
    if len(columns) < count:
        return None

    for metric_name in metric_names:
        if metric_name not in statement.index:
            continue
        values = pd.to_numeric(statement.loc[metric_name, columns], errors="coerce")
        if values.isna().any():
            return None
        return float(values.sum())

    return None


def compute_ebitda(statement: pd.DataFrame, start=0, count=4):
    ebitda = sum_statement_metric(statement, ["EBITDA"], start=start, count=count)
    if ebitda is not None:
        return ebitda

    ebit = sum_statement_metric(statement, ["EBIT", "Operating Income"], start=start, count=count)
    depreciation = sum_statement_metric(
        statement,
        [
            "Depreciation And Amortization",
            "Depreciation Amortization Depletion Income Statement",
            "Reconciled Depreciation",
        ],
        start=start,
        count=count,
    )
    if ebit is None or depreciation is None:
        return None
    return ebit + depreciation


def _get_sec_ttm_financials_with_fallback(ticker):
    try:
        return get_sec_ttm_financials(ticker)
    except SecRateLimited as e:
        logger.warning("%s SEC TTM rate limited; using Yahoo latest TTM where available: %s", ticker, e)
    except Exception as e:
        logger.warning("%s SEC TTM unavailable; using Yahoo latest TTM where available: %s", ticker, e)
    return {"Ticker": ticker}


def prefetch_sec_ttm_financials(tickers, cancel_event=None):
    started = time.monotonic()
    sec_financials_by_ticker = {}
    for batch, has_more in _batches(tickers):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("SEC TTM prefetch cancelled after %s tickers", len(sec_financials_by_ticker))
            break
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            results = list(executor.map(_get_sec_ttm_financials_with_fallback, batch))
        sec_financials_by_ticker.update((result["Ticker"], result) for result in results)

        if has_more:
            time.sleep(1)

    logger.info("SEC TTM prefetch completed: %s tickers in %.1fs", len(sec_financials_by_ticker), time.monotonic() - started)
    return sec_financials_by_ticker


def get_ttm_financials(ticker, yahoo_snapshot=None, fx_rates=None, sec_financials=None):
    sec_financials = sec_financials or _get_sec_ttm_financials_with_fallback(ticker)

    try:
        if yahoo_snapshot is not None:
            quarterly_income_stmt = yahoo_snapshot.quarterly_income_stmt
            quarterly_cashflow = yahoo_snapshot.quarterly_cashflow
            ticker_info = yahoo_snapshot.get_info()
        else:
            yahoo_ticker = YahooQueryTicker(ticker)
            quarterly_income_stmt = normalize_quarterly_statement(yahoo_ticker.quarterly_income_stmt)
            quarterly_cashflow = normalize_quarterly_statement(yahoo_ticker.quarterly_cashflow)
            ticker_info = get_yahoo_info(ticker)

        result = with_ttm_defaults(sec_financials)
        if quarterly_income_stmt.empty:
            logger.debug("%s Yahoo quarterly income statement unavailable; using SEC TTM where available", ticker)
            return result

        most_recent_quarter = quarterly_income_stmt.columns[0]
        yahoo_ebitda_ttm = compute_ebitda(quarterly_income_stmt)
        if yahoo_ebitda_ttm is not None:
            result["EBITDA TTM"] = yahoo_ebitda_ttm
        if result.get("EBITDA Prev TTM") is None:
            yahoo_ebitda_prev_ttm = compute_ebitda(quarterly_income_stmt, start=4, count=4)
            if yahoo_ebitda_prev_ttm is not None:
                result["EBITDA Prev TTM"] = yahoo_ebitda_prev_ttm

        result.update(
            {
                "Free Cash Flow TTM": sum_statement_metric(quarterly_cashflow, ["Free Cash Flow"]),
                "TTM Period End": pd.Timestamp(most_recent_quarter).strftime("%Y-%m-%d"),
            }
        )

        yahoo_metrics = {
            prefix: sum_statement_metric(quarterly_income_stmt, metric_names)
            for prefix, metric_names in _TTM_METRIC_NAMES.items()
        }
        yahoo_prev_metrics = {
            prefix: sum_statement_metric(quarterly_income_stmt, metric_names, start=4, count=4)
            for prefix, metric_names in _TTM_METRIC_NAMES.items()
        }
        for prefix, value in yahoo_metrics.items():
            if value is not None:
                result[f"{prefix} TTM"] = value
        for prefix, value in yahoo_prev_metrics.items():
            key = f"{prefix} Prev TTM"
            if result.get(key) is None and value is not None:
                result[key] = value

        financial_currency = ticker_info.get("financialCurrency")
        if financial_currency and financial_currency != "USD":
            fx_rate = (fx_rates or {}).get(financial_currency)
            if fx_rate is None:
                logger.warning("%s missing %s/USD FX rate; leaving financials in source currency", ticker, financial_currency)
                result["Financial Currency"] = financial_currency
                result["Source Financial Currency"] = financial_currency
            else:
                for key in YAHOO_FINANCIAL_KEYS:
                    if result[key] is not None:
                        result[key] *= fx_rate
                result["Financial Currency"] = "USD"
                result["Source Financial Currency"] = financial_currency
                result["Financial USD FX Rate"] = fx_rate

        return result
    except Exception as e:
        logger.warning("%s Yahoo latest TTM/cash flow skipped: %s", ticker, e)
        return with_ttm_defaults(sec_financials)


def compute_ttm_financials(tickers, yahoo_snapshots=None, fx_rates=None, sec_financials_by_ticker=None):
    yahoo_snapshots = yahoo_snapshots or {}
    if sec_financials_by_ticker is None:
        sec_financials_by_ticker = prefetch_sec_ttm_financials(tickers)
    ttm_financials_by_ticker = {}
    for batch, has_more in _batches(tickers):
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            results = list(
                executor.map(
                    lambda ticker: get_ttm_financials(
                        ticker,
                        yahoo_snapshots.get(ticker),
                        fx_rates,
                        sec_financials_by_ticker.get(ticker),
                    ),
                    batch,
                )
            )
        ttm_financials_by_ticker.update((result["Ticker"], result) for result in results)

        if has_more and any(ticker not in yahoo_snapshots for ticker in batch):
            time.sleep(1)

    unavailable_count = sum(
        1
        for ticker in tickers
        if not any(ttm_financials_by_ticker[ticker].get(key) is not None for key in YAHOO_FINANCIAL_KEYS)
    )
    if unavailable_count:
        logger.warning("TTM financials unavailable from SEC/Yahoo for %s out of %s tickers", unavailable_count, len(tickers))

    return _ticker_frame([ttm_financials_by_ticker[ticker] for ticker in tickers])


def get_and_parse_yahoo(tickers, cached_profiles=None, yahoo_snapshots=None):
    cached_profiles = cached_profiles or {}
    yahoo_snapshots = yahoo_snapshots or {}
    profiles_by_ticker = {}

    for ticker in tickers:
        cached_profile = cached_profiles.get(ticker)
        if cached_profile:
            profiles_by_ticker[ticker] = cached_profile
            continue
        snapshot = yahoo_snapshots.get(ticker)
        if snapshot:
            try:
                ticker_info = snapshot.get_info()
                profiles_by_ticker[ticker] = build_yahoo_profile(ticker_info.get("symbol", ticker), ticker_info)
            except Exception as e:
                logger.warning("%s snapshot profile unavailable; fetching Yahoo profile directly: %s", ticker, e)

    missing_tickers = [ticker for ticker in tickers if ticker not in profiles_by_ticker]
    for batch, has_more in _batches(missing_tickers):
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            futures = {executor.submit(get_yahoo_info, ticker): ticker for ticker in batch}
            for future in concurrent.futures.as_completed(futures):
                ticker = futures[future]
                try:
                    ticker_info = future.result()
                except Exception as e:
                    logger.warning("%s profile skipped: %s", ticker, e)
                    continue
                profile = build_yahoo_profile(ticker, ticker_info)
                profiles_by_ticker[profile["Ticker"]] = profile

        if has_more:
            time.sleep(1)

    missing_count = len(tickers) - len(profiles_by_ticker)
    if missing_count:
        logger.warning("Yahoo profiles missing for %s out of %s tickers", missing_count, len(tickers))

    return _ticker_frame([profiles_by_ticker[ticker] for ticker in tickers if ticker in profiles_by_ticker])
