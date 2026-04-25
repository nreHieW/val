import concurrent.futures
import time

import pandas as pd
from requests.exceptions import HTTPError
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import YAHOO_INFO_MAX_WORKERS, YAHOO_INFO_RETRIES, YAHOO_INFO_RETRY_SLEEP_SECONDS
from scrape.core.yahoo_client import yahoo_ticker


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
            yf_ticker = yahoo_ticker(ticker)
            quarterly_income_stmt = normalize_quarterly_statement(yf_ticker.quarterly_income_stmt)
            if quarterly_income_stmt.empty:
                raise ValueError(f"No quarterly income statement for {ticker}")

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
                "TTM Period End": pd.Timestamp(most_recent_quarter).strftime("%Y-%m-%d"),
            }
            return result
        except (HTTPError, YFRateLimitError):
            if attempt == YAHOO_INFO_RETRIES - 1:
                raise
            sleep_seconds = YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1)
            print(f"[WARN] Yahoo request failed for {ticker} TTM; retrying in {sleep_seconds:.1f}s")
            time.sleep(sleep_seconds)


def compute_ttm_financials(tickers):
    ttm_financials_by_ticker = {}
    for i in range(0, len(tickers), YAHOO_INFO_MAX_WORKERS):
        batch = tickers[i : i + YAHOO_INFO_MAX_WORKERS]
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            results = list(executor.map(get_ttm_financials, batch))
        for result in results:
            ttm_financials_by_ticker[result["Ticker"]] = result

        if i + YAHOO_INFO_MAX_WORKERS < len(tickers):
            time.sleep(1)

    ordered_financials = [ttm_financials_by_ticker[ticker] for ticker in tickers if ticker in ttm_financials_by_ticker]
    if not ordered_financials:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_financials).set_index("Ticker")


def get_info(ticker):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            ticker_info = yahoo_ticker(ticker).get_info()
            return build_yahoo_profile(ticker, ticker_info)
        except (HTTPError, YFRateLimitError):
            if attempt == YAHOO_INFO_RETRIES - 1:
                raise
            sleep_seconds = YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1)
            print(f"[WARN] Yahoo request failed for {ticker}; retrying in {sleep_seconds:.1f}s")
            time.sleep(sleep_seconds)


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
                profiles_by_ticker[result["Ticker"]] = result

            if i + YAHOO_INFO_MAX_WORKERS < len(missing_tickers):
                time.sleep(1)

    ordered_profiles = [profiles_by_ticker[ticker] for ticker in tickers if ticker in profiles_by_ticker]
    if not ordered_profiles:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_profiles).set_index("Ticker")
