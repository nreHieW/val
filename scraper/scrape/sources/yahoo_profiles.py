import concurrent.futures
import logging
import random
import time
from functools import lru_cache

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import YAHOO_INFO_MAX_WORKERS, YAHOO_INFO_RETRIES, YAHOO_INFO_RETRY_SLEEP_SECONDS

logger = logging.getLogger(__name__)

def _retry_sleep(attempt: int):
    time.sleep(YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1) + random.uniform(0, 1))


@lru_cache(maxsize=10000)
def get_yahoo_info(ticker):
    return yf.Ticker(ticker).get_info()


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
    if statement is None or statement.empty:
        return pd.DataFrame()

    statement = statement.copy()
    statement = statement.loc[~statement.index.duplicated(keep="first")]
    ordered_columns = sorted(statement.columns, key=lambda column: pd.Timestamp(column), reverse=True)
    return statement.loc[:, ordered_columns].fillna(0)


def sum_statement_metric(statement: pd.DataFrame, metric_names: list[str], start=0, count=4):
    columns = list(statement.columns[start : start + count])

    for metric_name in metric_names:
        if metric_name in statement.index:
            values = pd.to_numeric(statement.loc[metric_name, columns], errors="coerce").fillna(0)
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


def get_ttm_financials(ticker):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            yf_ticker = yf.Ticker(ticker)
            quarterly_income_stmt = normalize_quarterly_statement(yf_ticker.quarterly_income_stmt)
            quarterly_cashflow = normalize_quarterly_statement(yf_ticker.quarterly_cashflow)
            if quarterly_income_stmt.empty:
                return None

            most_recent_quarter = quarterly_income_stmt.columns[0]
            result = {
                "Ticker": ticker,
                "Revenue TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["Total Revenue", "Operating Revenue", "Revenue"],
                ),
                "Revenue Prev TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["Total Revenue", "Operating Revenue", "Revenue"],
                    start=4,
                    count=4,
                ),
                "Net Income TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    [
                        "Net Income Common Stockholders",
                        "Net Income Including Noncontrolling Interests",
                        "Net Income",
                    ],
                ),
                "Net Income Prev TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    [
                        "Net Income Common Stockholders",
                        "Net Income Including Noncontrolling Interests",
                        "Net Income",
                    ],
                    start=4,
                    count=4,
                ),
                "EBITDA TTM": compute_ebitda(quarterly_income_stmt),
                "EBITDA Prev TTM": compute_ebitda(quarterly_income_stmt, start=4, count=4),
                "EBIT TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["EBIT", "Operating Income"],
                ),
                "EBIT Prev TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["EBIT", "Operating Income"],
                    start=4,
                    count=4,
                ),
                "Free Cash Flow TTM": sum_statement_metric(quarterly_cashflow, ["Free Cash Flow"]),
                "TTM Period End": pd.Timestamp(most_recent_quarter).strftime("%Y-%m-%d"),
            }
            return result
        except YFRateLimitError:
            if attempt == YAHOO_INFO_RETRIES - 1:
                logger.debug("%s TTM skipped: Yahoo rate limited after %s attempts", ticker, YAHOO_INFO_RETRIES)
                return None

            _retry_sleep(attempt)
        except Exception as e:
            logger.debug("%s TTM skipped: %s", ticker, e)
            return None


def compute_ttm_financials(tickers):
    ttm_financials_by_ticker = {}
    for i in range(0, len(tickers), YAHOO_INFO_MAX_WORKERS):
        batch = tickers[i : i + YAHOO_INFO_MAX_WORKERS]
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            results = list(executor.map(get_ttm_financials, batch))
        for result in results:
            if result:
                ttm_financials_by_ticker[result["Ticker"]] = result

        if i + YAHOO_INFO_MAX_WORKERS < len(tickers):
            time.sleep(1)

    missing_count = len(tickers) - len(ttm_financials_by_ticker)
    if missing_count:
        logger.warning("TTM financials missing for %s out of %s tickers", missing_count, len(tickers))

    ordered_financials = [ttm_financials_by_ticker[ticker] for ticker in tickers if ticker in ttm_financials_by_ticker]
    if not ordered_financials:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_financials).set_index("Ticker")


def get_info(ticker):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            ticker_info = get_yahoo_info(ticker)
            return build_yahoo_profile(ticker, ticker_info)
        except YFRateLimitError:
            if attempt == YAHOO_INFO_RETRIES - 1:
                logger.debug("%s profile skipped: Yahoo rate limited after %s attempts", ticker, YAHOO_INFO_RETRIES)
                return None

            _retry_sleep(attempt)
        except Exception as e:
            logger.debug("%s profile skipped: %s", ticker, e)
            return None


def get_and_parse_yahoo(tickers, cached_profiles=None):
    cached_profiles = cached_profiles or {}
    profiles_by_ticker = {}

    for ticker in tickers:
        cached_profile = cached_profiles.get(ticker)
        if cached_profile:
            profiles_by_ticker[ticker] = cached_profile

    missing_tickers = [ticker for ticker in tickers if ticker not in profiles_by_ticker]
    if missing_tickers:
        for i in range(0, len(missing_tickers), YAHOO_INFO_MAX_WORKERS):
            batch = missing_tickers[i : i + YAHOO_INFO_MAX_WORKERS]
            with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
                results = list(executor.map(get_info, batch))
            for result in results:
                if result:
                    profiles_by_ticker[result["Ticker"]] = result

            if i + YAHOO_INFO_MAX_WORKERS < len(missing_tickers):
                time.sleep(1)

    missing_count = len(tickers) - len(profiles_by_ticker)
    if missing_count:
        logger.warning("Yahoo profiles missing for %s out of %s tickers", missing_count, len(tickers))

    ordered_profiles = [profiles_by_ticker[ticker] for ticker in tickers if ticker in profiles_by_ticker]
    if not ordered_profiles:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_profiles).set_index("Ticker")
