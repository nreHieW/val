import concurrent.futures
import logging
from dataclasses import dataclass

import pandas as pd
from yahooquery import Ticker

from scrape.core.config import YAHOOQUERY_BATCH_SIZE
from scrape.sources.yahoo_profiles import normalize_quarterly_statement
from scrape.sources.yahooquery_adapter import INFO_MODULES, YahooQueryTicker, statement_to_wide_shape

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
    history: pd.DataFrame


def _history_for_symbol(history: pd.DataFrame, yahoo_symbol: str) -> pd.DataFrame:
    if not isinstance(history, pd.DataFrame) or history.empty or not isinstance(history.index, pd.MultiIndex):
        return pd.DataFrame()
    if yahoo_symbol not in history.index.get_level_values(0):
        return pd.DataFrame()
    return history.xs(yahoo_symbol, level=0, drop_level=False)


def get_yahoo_snapshots(tickers: list[str]) -> dict[str, YahooSnapshot]:
    snapshots: dict[str, YahooSnapshot] = {}
    for i in range(0, len(tickers), YAHOOQUERY_BATCH_SIZE):
        batch = tickers[i : i + YAHOOQUERY_BATCH_SIZE]
        yahoo_symbols = [ticker.replace(".", "-") for ticker in batch]
        client = Ticker(yahoo_symbols, asynchronous=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            modules_future = executor.submit(client.get_modules, INFO_MODULES)
            quarterly_income_future = executor.submit(client.income_statement, frequency="q")
            quarterly_balance_future = executor.submit(client.balance_sheet, frequency="q")
            quarterly_cashflow_future = executor.submit(client.cash_flow, frequency="q")
            annual_income_future = executor.submit(client.income_statement)
            history_future = executor.submit(client.history, period="1y", interval="1d")

            modules = modules_future.result()
            quarterly_income = quarterly_income_future.result()
            quarterly_balance = quarterly_balance_future.result()
            quarterly_cashflow = quarterly_cashflow_future.result()
            annual_income = annual_income_future.result()
            history = history_future.result()

        for ticker, yahoo_symbol in zip(batch, yahoo_symbols):
            try:
                yahoo_ticker = YahooQueryTicker(
                    ticker,
                    modules=modules.get(yahoo_symbol) or modules.get(ticker),
                    quarterly_income_stmt=normalize_quarterly_statement(
                        statement_to_wide_shape(quarterly_income, "3M", yahoo_symbol)
                    ),
                    quarterly_balance_sheet=statement_to_wide_shape(quarterly_balance, "3M", yahoo_symbol),
                    quarterly_cashflow=normalize_quarterly_statement(
                        statement_to_wide_shape(quarterly_cashflow, "3M", yahoo_symbol)
                    ),
                    income_stmt=statement_to_wide_shape(annual_income, "12M", yahoo_symbol),
                    history=_history_for_symbol(history, yahoo_symbol),
                )
                snapshots[ticker] = YahooSnapshot(
                    ticker=ticker,
                    yahoo_ticker=yahoo_ticker,
                    info=yahoo_ticker.get_info(),
                    quarterly_income_stmt=yahoo_ticker.quarterly_income_stmt,
                    quarterly_balance_sheet=yahoo_ticker.quarterly_balance_sheet,
                    quarterly_cashflow=yahoo_ticker.quarterly_cashflow,
                    income_stmt=yahoo_ticker.income_stmt,
                    history=yahoo_ticker.history(),
                )
            except Exception as e:
                logger.debug("%s yahooquery snapshot skipped: %s", ticker, e)

    missing_count = len(tickers) - len(snapshots)
    if missing_count:
        logger.warning("Yahoo snapshots missing for %s out of %s tickers", missing_count, len(tickers))
    return snapshots
