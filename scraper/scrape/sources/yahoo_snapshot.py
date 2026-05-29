import concurrent.futures
import logging
from dataclasses import dataclass

import pandas as pd

from scrape.core.config import YAHOO_INFO_MAX_WORKERS
from scrape.sources.yahoo_profiles import normalize_quarterly_statement
from scrape.sources.yahooquery_adapter import YahooQueryTicker

logger = logging.getLogger(__name__)


@dataclass
class YahooSnapshot:
    ticker: str
    yahoo_ticker: YahooQueryTicker
    info: dict
    quarterly_income_stmt: pd.DataFrame
    quarterly_balance_sheet: pd.DataFrame
    quarterly_cashflow: pd.DataFrame
    income_stmt: pd.DataFrame

    @property
    def symbol(self) -> str:
        return self.info.get("symbol") or self.ticker


def get_yahoo_snapshot(ticker: str) -> YahooSnapshot | None:
    yahoo_ticker = YahooQueryTicker(ticker)
    try:
        info = yahoo_ticker.get_info()
        quarterly_income_stmt = normalize_quarterly_statement(yahoo_ticker.quarterly_income_stmt)
        quarterly_balance_sheet = yahoo_ticker.quarterly_balance_sheet
        quarterly_cashflow = normalize_quarterly_statement(yahoo_ticker.quarterly_cashflow)
        income_stmt = yahoo_ticker.income_stmt
    except Exception as e:
        logger.debug("%s yahooquery snapshot skipped: %s", ticker, e)
        return None

    return YahooSnapshot(
        ticker=ticker,
        yahoo_ticker=yahoo_ticker,
        info=info,
        quarterly_income_stmt=quarterly_income_stmt,
        quarterly_balance_sheet=quarterly_balance_sheet,
        quarterly_cashflow=quarterly_cashflow,
        income_stmt=income_stmt,
    )


def get_yahoo_snapshots(tickers: list[str]) -> dict[str, YahooSnapshot]:
    snapshots: dict[str, YahooSnapshot] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
        futures = {executor.submit(get_yahoo_snapshot, ticker): ticker for ticker in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                snapshot = future.result()
            except Exception as e:
                logger.debug("%s yahooquery snapshot failed: %s", ticker, e)
                continue
            if snapshot:
                snapshots[ticker] = snapshot

    missing_count = len(tickers) - len(snapshots)
    if missing_count:
        logger.warning("Yahoo snapshots missing for %s out of %s tickers", missing_count, len(tickers))
    return snapshots
