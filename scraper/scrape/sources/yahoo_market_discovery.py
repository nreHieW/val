import logging
import time
from datetime import timedelta

import yfinance as yf
from yfinance import EquityQuery, screen
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import YAHOO_INFO_RETRIES, YAHOO_INFO_RETRY_SLEEP_SECONDS
from scrape.sources.yahoo_profiles import get_yahoo_info

logger = logging.getLogger(__name__)

SECTOR_KEYS = [
    "basic-materials",
    "communication-services",
    "consumer-cyclical",
    "consumer-defensive",
    "energy",
    "financial-services",
    "healthcare",
    "industrials",
    "real-estate",
    "technology",
    "utilities",
]

PERFORMANCE_PERIODS = {
    "daily": 1,
    "weekly": 7,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
}

SIMILAR_COMPANY_SCREEN_SIZE = 250


def _yahoo_call(label, fn, retry_none=False):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            result = fn()
            if result is not None or not retry_none:
                return result
        except YFRateLimitError:
            if attempt == YAHOO_INFO_RETRIES - 1:
                logger.debug("%s skipped: Yahoo rate limited after %s attempts", label, YAHOO_INFO_RETRIES)
                return None
        except Exception as e:
            logger.debug("%s skipped: %s", label, e)
            return None
        time.sleep(YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1))
    return None


def get_similar_companies(source):
    info = _yahoo_call(f"{source} similar companies", lambda: get_yahoo_info(source))
    if info is None:
        return None
    industry = info["industry"].replace(" - ", "—")
    query = EquityQuery(
        "and",
        [
            EquityQuery("eq", ["sector", info["sector"]]),
            EquityQuery("eq", ["industry", industry]),
            EquityQuery("is-in", ["exchange", "NMS", "NYQ"]),
        ],
    )
    df = screen(query, size=SIMILAR_COMPANY_SCREEN_SIZE, sortField="intradaymarketcap")
    similar_tickers = [quote["symbol"] for quote in df["quotes"] if quote.get("symbol") != source and quote.get("symbol")]
    return {
        "Ticker": source,
        "sector": info["sector"],
        "industry": info["industry"],
        "similar_tickers": similar_tickers,
    }


def _performance_percent(closes, days):
    if len(closes) < 2:
        return None
    end_date = closes.index[-1]
    start = closes[closes.index >= end_date - timedelta(days=days)].iloc[0]
    return float((closes.iloc[-1] / start - 1) * 100)


def _industry_performance(symbol):
    empty = {name: None for name in [*PERFORMANCE_PERIODS, "ytd"]}
    history = _yahoo_call(
        f"{symbol} industry performance",
        lambda: yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True),
    )
    if history is None:
        return empty

    closes = history["Close"].dropna()
    if len(closes) < 2:
        return empty

    performance = {name: _performance_percent(closes, days) for name, days in PERFORMANCE_PERIODS.items()}
    ytd = closes[closes.index.year == closes.index[-1].year]
    performance["ytd"] = None if len(ytd) < 2 else float((ytd.iloc[-1] / ytd.iloc[0] - 1) * 100)
    return performance


def get_sector_industries():
    industries = []
    for sector_key in SECTOR_KEYS:
        sector_data = _yahoo_call(
            f"{sector_key} sector industries",
            lambda: (lambda s: (s, s.industries) if s.industries is not None else None)(yf.Sector(sector_key)),
            retry_none=True,
        )
        if sector_data is None:
            logger.warning("No industries found for sector %s", sector_key)
            continue
        sector, sector_industries = sector_data

        for industry_key, row in sector_industries.iterrows():
            industry = yf.Industry(industry_key)
            top_companies_df = _yahoo_call(
                f"{industry_key} top companies",
                lambda: industry.top_companies,
                retry_none=True,
            )
            top_companies = (
                []
                if top_companies_df is None
                else top_companies_df.reset_index(names="symbol").to_dict(orient="records")
            )
            industries.append(
                {
                    "sector_key": sector_key,
                    "sector_name": sector.name,
                    "industry_key": industry_key,
                    "industry_name": row["name"],
                    "symbol": row["symbol"],
                    "market_weight": row["market weight"],
                    "overview": industry.overview,
                    "top_companies": top_companies,
                    "performance_pct": _industry_performance(row["symbol"]),
                }
            )
    return industries
