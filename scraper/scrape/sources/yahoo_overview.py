from datetime import datetime, timedelta, timezone

import pandas as pd

from scrape.sources.yahooquery_adapter import yahooquery_close_series


def _clean_value(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return value


def _records_from_dataframe(df: pd.DataFrame, limit: int | None = None):
    normalized = df.reset_index()
    records = normalized.to_dict(orient="records")
    if limit is not None:
        records = records[:limit]
    return [{str(k): _clean_value(v) for k, v in record.items()} for record in records]


def _historical_pe_range(close: pd.Series, ttm_eps: float, days: int):
    if close.empty:
        return None
    cutoff = pd.Timestamp(datetime.now() - timedelta(days=days))
    period_close = close[close.index >= cutoff]
    if period_close.empty:
        return None
    pe = (period_close / ttm_eps).replace([float("inf"), float("-inf")], pd.NA).dropna()
    pe = pe[pe > 0]
    if pe.empty:
        return None
    return {
        "low": round(float(pe.min()), 2),
        "mean": round(float(pe.mean()), 2),
        "high": round(float(pe.max()), 2),
        "observations": int(pe.count()),
    }


def build_yahoo_overview(yahoo_ticker, info: dict):
    symbol = info.get("symbol") or yahoo_ticker.ticker
    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    previous_close = info.get("previousClose")
    analyst_targets = {
        "low": info.get("targetLowPrice"),
        "high": info.get("targetHighPrice"),
        "mean": info.get("targetMeanPrice"),
        "median": info.get("targetMedianPrice"),
    }
    earnings_records = _records_from_dataframe(yahoo_ticker.get_earnings_estimate())
    earnings_by_period = {
        str(record["period"]): record
        for record in earnings_records
        if record.get("period") is not None
    }
    recommendations = next(
        (
            record
            for record in _records_from_dataframe(yahoo_ticker.get_recommendations_summary(), limit=4)
            if record.get("period") == "0m"
        ),
        None,
    )
    major_holders = {
        str(index): _clean_value(value)
        for index, value in yahoo_ticker.get_major_holders()["Value"].items()
    }
    insider_roster = _records_from_dataframe(yahoo_ticker.get_insider_roster_holders(), limit=10)
    target_reference = analyst_targets["median"] or analyst_targets["mean"]
    target_upside = (target_reference / current_price) - 1 if target_reference and current_price else None
    ttm_eps = info.get("epsTrailingTwelveMonths")
    trailing_pe = info.get("trailingPE")
    if (not ttm_eps or ttm_eps <= 0) and trailing_pe and trailing_pe > 0 and current_price:
        ttm_eps = current_price / trailing_pe
    historical_pe = {"90Day": None, "1Year": None}
    if ttm_eps and ttm_eps > 0:
        close = yahooquery_close_series(yahoo_ticker.history(period="1y", interval="1d"))
        historical_pe = {
            "90Day": _historical_pe_range(close, ttm_eps, 90),
            "1Year": _historical_pe_range(close, ttm_eps, 365),
        }

    return {
        "Ticker": symbol,
        "profile": {
            "name": info.get("longName") or info.get("shortName"),
            "shortName": info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "website": info.get("website"),
            "summary": info.get("longBusinessSummary"),
        },
        "market": {
            "price": current_price,
            "dayChangePercent": (current_price / previous_close) - 1 if current_price and previous_close else None,
            "marketCap": info.get("marketCap"),
            "enterpriseValue": info.get("enterpriseValue"),
            "beta": info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
        },
        "valuation": {
            "trailingPe": info.get("trailingPE"),
            "forwardPe": info.get("forwardPE"),
            "priceToSales": info.get("priceToSalesTrailing12Months"),
            "enterpriseToRevenue": info.get("enterpriseToRevenue"),
            "enterpriseToEbitda": info.get("enterpriseToEbitda"),
            "operatingMargins": info.get("operatingMargins"),
            "historicalPe": historical_pe,
        },
        "analyst": {
            "targets": {k: _clean_value(analyst_targets.get(k)) for k in ["low", "high", "mean", "median"]},
            "targetUpside": _clean_value(target_upside),
            "recommendations": {"current": recommendations},
        },
        "eps": {
            "estimates": {
                "currentYear": earnings_by_period.get("0y"),
                "nextYear": earnings_by_period.get("+1y"),
                "currentQuarter": earnings_by_period.get("0q"),
            },
        },
        "ownership": {
            "insidersPercentHeld": major_holders.get("insidersPercentHeld"),
            "institutionsPercentHeld": major_holders.get("institutionsPercentHeld"),
            "institutionsCount": major_holders.get("institutionsCount"),
            "insiderRoster": insider_roster,
        },
    }
