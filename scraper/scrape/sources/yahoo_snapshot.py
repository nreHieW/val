import concurrent.futures
import logging
import time

import pandas as pd
from yahooquery import Ticker

from scrape.core.config import (
    YAHOOQUERY_BATCH_SIZE,
    YAHOOQUERY_MAX_WORKERS,
)
from scrape.core.policies import YAHOO_SNAPSHOT
from scrape.sources.yahoo_profiles import normalize_quarterly_statement
from scrape.sources.yahooquery_adapter import INFO_MODULES, YahooQueryTicker, statement_to_wide_shape

logger = logging.getLogger(__name__)
_PROGRESS_INTERVAL_BATCHES = 10


class YahooSnapshotRejected(RuntimeError):
    pass


def _get_yahoo_snapshot_batch(batch: list[str]) -> dict[str, YahooQueryTicker]:
    yahoo_symbols = [ticker.replace(".", "-") for ticker in batch]
    client = Ticker(yahoo_symbols, asynchronous=True, max_workers=YAHOOQUERY_MAX_WORKERS)
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

    snapshots: dict[str, YahooQueryTicker] = {}
    for ticker, yahoo_symbol in zip(batch, yahoo_symbols):
        try:
            symbol_history = pd.DataFrame()
            if (
                isinstance(history, pd.DataFrame)
                and not history.empty
                and isinstance(history.index, pd.MultiIndex)
                and yahoo_symbol in history.index.get_level_values(0)
            ):
                symbol_history = history.xs(yahoo_symbol, level=0, drop_level=False)
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
                history=symbol_history,
            )
            yahoo_ticker.get_info()
            snapshots[ticker] = yahoo_ticker
        except Exception as e:
            logger.warning("%s yahooquery snapshot skipped: %s", ticker, e)
    return snapshots


def _collect_yahoo_snapshot_batch(batch, batch_number, total_batches):
    try:
        return _get_yahoo_snapshot_batch(batch)
    except Exception as e:
        logger.warning("Yahoo snapshot batch %s of %s failed: %s", batch_number, total_batches, e)
        return {}


def get_yahoo_snapshots(tickers: list[str]) -> dict[str, YahooQueryTicker]:
    snapshots: dict[str, YahooQueryTicker] = {}
    total_batches = (len(tickers) + YAHOOQUERY_BATCH_SIZE - 1) // YAHOOQUERY_BATCH_SIZE
    consecutive_empty_batches = 0
    for i in range(0, len(tickers), YAHOOQUERY_BATCH_SIZE):
        batch_number = i // YAHOOQUERY_BATCH_SIZE + 1
        batch = tickers[i : i + YAHOOQUERY_BATCH_SIZE]
        batch_started = time.monotonic()
        batch_snapshots = _collect_yahoo_snapshot_batch(batch, batch_number, total_batches)
        if not batch_snapshots:
            logger.warning(
                "Yahoo snapshot batch %s of %s returned no snapshots; cooling down for %.1fs before one retry",
                batch_number,
                total_batches,
                YAHOO_SNAPSHOT.failure_cooldown_seconds,
            )
            time.sleep(YAHOO_SNAPSHOT.failure_cooldown_seconds)
            batch_snapshots = _collect_yahoo_snapshot_batch(batch, batch_number, total_batches)
        snapshots.update(batch_snapshots)
        if batch_snapshots:
            consecutive_empty_batches = 0
        else:
            consecutive_empty_batches += 1
        if len(batch_snapshots) != len(batch) or batch_number % _PROGRESS_INTERVAL_BATCHES == 0 or batch_number == total_batches:
            log = logger.warning if len(batch_snapshots) != len(batch) else logger.info
            log(
                "Yahoo snapshot batch %s of %s: %s of %s snapshots collected (%s cumulative) in %.1fs",
                batch_number,
                total_batches,
                len(batch_snapshots),
                len(batch),
                len(snapshots),
                time.monotonic() - batch_started,
            )
        if consecutive_empty_batches >= YAHOO_SNAPSHOT.max_consecutive_empty_batches:
            raise YahooSnapshotRejected(
                f"Yahoo rejected {consecutive_empty_batches} consecutive snapshot batches; stopping before database writes"
            )
        if i + YAHOOQUERY_BATCH_SIZE < len(tickers):
            time.sleep(YAHOO_SNAPSHOT.batch_sleep_seconds)

    missing_count = len(tickers) - len(snapshots)
    if missing_count:
        logger.warning("Yahoo snapshots missing for %s out of %s tickers", missing_count, len(tickers))
    return snapshots
