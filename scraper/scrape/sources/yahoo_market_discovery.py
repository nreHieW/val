import logging

import yfinance as yf
from yfinance import EquityQuery, screen

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
    "daily": "5d",
    "weekly": "5d",
    "1mo": "1mo",
    "3mo": "3mo",
    "6mo": "6mo",
    "ytd": "ytd",
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


def _performance_percent(symbol, period, daily=False):
    history = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
    closes = history["Close"].dropna()
    if len(closes) < 2:
        return None
    start = closes.iloc[-2] if daily else closes.iloc[0]
    return float((closes.iloc[-1] / start - 1) * 100)


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
                    "performance_pct": {
                        name: _performance_percent(row["symbol"], period, daily=name == "daily")
                        for name, period in PERFORMANCE_PERIODS.items()
                    },
                }
            )
    return industries
