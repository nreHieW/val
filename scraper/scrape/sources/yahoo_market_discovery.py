import logging
from datetime import timedelta

import yfinance as yf
from yfinance import EquityQuery, screen
from yfinance.exceptions import YFRateLimitError

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


def get_similar_companies(source):
    info = yf.Ticker(source).get_info()
    industry = info["industry"].replace(" - ", "—")
    query = EquityQuery(
        "and",
        [
            EquityQuery("eq", ["sector", info["sector"]]),
            EquityQuery("eq", ["industry", industry]),
            EquityQuery("is-in", ["exchange", "NMS", "NYQ"]),
        ],
    )
    df = screen(query, size=10, sortField="intradaymarketcap")
    companies = [quote for quote in df["quotes"] if quote.get("symbol") != source]
    return {
        "Ticker": source,
        "sector": info["sector"],
        "industry": info["industry"],
        "similar_companies": companies,
        "similar_tickers": [company["symbol"] for company in companies],
    }


def _performance_percent(closes, days):
    if len(closes) < 2:
        return None
    end_date = closes.index[-1]
    start = closes[closes.index >= end_date - timedelta(days=days)].iloc[0]
    return float((closes.iloc[-1] / start - 1) * 100)


def _industry_performance(symbol):
    empty = {name: None for name in [*PERFORMANCE_PERIODS, "ytd"]}
    try:
        history = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
    except YFRateLimitError:
        logger.warning("Yahoo rate limited industry performance for %s", symbol)
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
        sector = yf.Sector(sector_key)
        for industry_key, row in sector.industries.iterrows():
            industry = yf.Industry(industry_key)
            top_companies = industry.top_companies.reset_index(names="symbol").to_dict(orient="records")
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
