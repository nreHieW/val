import concurrent.futures
import logging
from dataclasses import dataclass

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import YAHOO_INFO_MAX_WORKERS
from scrape.core.rate_limit import yahoo_call
from scrape.sources.yahoo_profiles import normalize_quarterly_statement

logger = logging.getLogger(__name__)


@dataclass
class YahooSnapshot:
    ticker: str
    yf_ticker: yf.Ticker
    info: dict
    quarterly_income_stmt: pd.DataFrame
    quarterly_balance_sheet: pd.DataFrame
    quarterly_cashflow: pd.DataFrame
    income_stmt: pd.DataFrame

    @property
    def symbol(self) -> str:
        return self.info.get("symbol") or self.ticker


def _safe_statement(fetcher, label: str) -> pd.DataFrame:
    try:
        return yahoo_call(fetcher)
    except YFRateLimitError:
        raise
    except Exception as e:
        logger.debug("%s unavailable: %s", label, e)
        return pd.DataFrame()


def get_yahoo_snapshot(ticker: str) -> YahooSnapshot | None:
    yf_ticker = yf.Ticker(ticker)
    try:
        info = yahoo_call(lambda: yf_ticker.get_info()) or {}
        quarterly_income_stmt = normalize_quarterly_statement(
            _safe_statement(lambda: yf_ticker.quarterly_income_stmt, f"{ticker} quarterly income statement")
        )
        quarterly_balance_sheet = _safe_statement(lambda: yf_ticker.quarterly_balance_sheet, f"{ticker} quarterly balance sheet")
        quarterly_cashflow = normalize_quarterly_statement(
            _safe_statement(lambda: yf_ticker.quarterly_cashflow, f"{ticker} quarterly cashflow")
        )
        income_stmt = _safe_statement(lambda: yf_ticker.income_stmt, f"{ticker} income statement")
    except YFRateLimitError:
        logger.debug("%s snapshot skipped: Yahoo rate limited", ticker)
        return None
    except Exception as e:
        logger.debug("%s snapshot skipped: %s", ticker, e)
        return None

    return YahooSnapshot(
        ticker=ticker,
        yf_ticker=yf_ticker,
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
                logger.debug("%s snapshot failed: %s", ticker, e)
                continue
            if snapshot:
                snapshots[ticker] = snapshot

    missing_count = len(tickers) - len(snapshots)
    if missing_count:
        logger.warning("Yahoo snapshots missing for %s out of %s tickers", missing_count, len(tickers))
    return snapshots
