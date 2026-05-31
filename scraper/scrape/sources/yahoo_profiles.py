import concurrent.futures
import logging
import time
from functools import lru_cache

import pandas as pd

from scrape.core.config import YAHOO_INFO_MAX_WORKERS
from scrape.sources.sec_companyfacts import get_sec_ttm_financials
from scrape.sources.yahooquery_adapter import YahooQueryTicker

logger = logging.getLogger(__name__)


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
    if statement is None or statement.empty:
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
        if metric_name in statement.index:
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


def get_ttm_financials(ticker, yahoo_snapshot=None):
    try:
        sec_financials = get_sec_ttm_financials(ticker)
    except Exception as e:
        logger.warning("%s SEC TTM skipped: %s", ticker, e)
        return None

    try:
        if yahoo_snapshot is not None:
            quarterly_income_stmt = yahoo_snapshot.quarterly_income_stmt
            quarterly_cashflow = yahoo_snapshot.quarterly_cashflow
        else:
            yahoo_ticker = YahooQueryTicker(ticker)
            quarterly_income_stmt = normalize_quarterly_statement(yahoo_ticker.quarterly_income_stmt)
            quarterly_cashflow = normalize_quarterly_statement(yahoo_ticker.quarterly_cashflow)
        if quarterly_income_stmt.empty:
            logger.warning("%s Yahoo quarterly income statement unavailable", ticker)
            return {**sec_financials, "EBITDA TTM": None, "EBITDA Prev TTM": None, "Free Cash Flow TTM": None}

        most_recent_quarter = quarterly_income_stmt.columns[0]
        result = {
            **sec_financials,
            "EBITDA TTM": compute_ebitda(quarterly_income_stmt),
            "EBITDA Prev TTM": compute_ebitda(quarterly_income_stmt, start=4, count=4),
            "Free Cash Flow TTM": sum_statement_metric(quarterly_cashflow, ["Free Cash Flow"]),
            "TTM Period End": pd.Timestamp(most_recent_quarter).strftime("%Y-%m-%d"),
        }

        for key, value in {
            "Revenue TTM": sum_statement_metric(quarterly_income_stmt, ["Total Revenue", "Operating Revenue", "Revenue"]),
            "Net Income TTM": sum_statement_metric(
                quarterly_income_stmt,
                ["Net Income Common Stockholders", "Net Income Including Noncontrolling Interests", "Net Income"],
            ),
            "EBIT TTM": sum_statement_metric(quarterly_income_stmt, ["EBIT", "Operating Income"]),
        }.items():
            if value is None:
                logger.warning("%s %s unavailable from Yahoo; using SEC value", ticker, key)
            else:
                result[key] = value

        for key in ["EBITDA TTM", "EBITDA Prev TTM", "Free Cash Flow TTM"]:
            if result[key] is None:
                logger.warning("%s %s unavailable from Yahoo", ticker, key)
        return result
    except Exception as e:
        logger.warning("%s Yahoo latest TTM/cash flow skipped: %s", ticker, e)
        return {**sec_financials, "EBITDA TTM": None, "EBITDA Prev TTM": None, "Free Cash Flow TTM": None}


def compute_ttm_financials(tickers, yahoo_snapshots=None):
    yahoo_snapshots = yahoo_snapshots or {}
    ttm_financials_by_ticker = {}
    for i in range(0, len(tickers), YAHOO_INFO_MAX_WORKERS):
        batch = tickers[i : i + YAHOO_INFO_MAX_WORKERS]
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            results = list(executor.map(lambda ticker: get_ttm_financials(ticker, yahoo_snapshots.get(ticker)), batch))
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
        if snapshot and snapshot.info:
            profiles_by_ticker[ticker] = build_yahoo_profile(snapshot.info.get("symbol", ticker), snapshot.info)

    missing_tickers = [ticker for ticker in tickers if ticker not in profiles_by_ticker]
    if missing_tickers:
        for i in range(0, len(missing_tickers), YAHOO_INFO_MAX_WORKERS):
            batch = missing_tickers[i : i + YAHOO_INFO_MAX_WORKERS]
            with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
                futures = {executor.submit(get_yahoo_info, ticker): ticker for ticker in batch}
                for future in concurrent.futures.as_completed(futures):
                    ticker = futures[future]
                    try:
                        ticker_info = future.result()
                    except Exception as e:
                        logger.debug("%s profile skipped: %s", ticker, e)
                        continue
                    if ticker_info:
                        profile = build_yahoo_profile(ticker, ticker_info)
                        profiles_by_ticker[profile["Ticker"]] = profile

            if i + YAHOO_INFO_MAX_WORKERS < len(missing_tickers):
                time.sleep(1)

    missing_count = len(tickers) - len(profiles_by_ticker)
    if missing_count:
        logger.warning("Yahoo profiles missing for %s out of %s tickers", missing_count, len(tickers))

    ordered_profiles = [profiles_by_ticker[ticker] for ticker in tickers if ticker in profiles_by_ticker]
    if not ordered_profiles:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_profiles).set_index("Ticker")
