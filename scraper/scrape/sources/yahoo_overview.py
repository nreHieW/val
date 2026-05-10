from datetime import datetime, timezone

import pandas as pd


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


def _dict_from_dataframe(df: pd.DataFrame):
    if len(df.columns) == 1:
        value_col = df.columns[0]
        return {
            str(index): _clean_value(value)
            for index, value in df[value_col].items()
        }
    return {
        str(record.get("Breakdown", record.get("index", i))): _clean_value(record.get("Value"))
        for i, record in enumerate(df.reset_index().to_dict(orient="records"))
    }


def _extract_recommendation_mix(df: pd.DataFrame):
    records = _records_from_dataframe(df, limit=4)
    for record in records:
        if record.get("period") == "0m":
            return record
    raise ValueError("Yahoo recommendations summary missing period")


def _extract_earnings_estimates(df: pd.DataFrame):
    records = _records_from_dataframe(df)
    by_period = {str(record.get("period")): record for record in records if record.get("period") is not None}
    return {
        "currentYear": by_period.get("0y"),
        "nextYear": by_period.get("+1y"),
        "currentQuarter": by_period.get("0q"),
    }


def build_yahoo_overview(yf_ticker, info: dict):
    symbol = info.get("symbol") or yf_ticker.ticker
    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    analyst_targets = yf_ticker.get_analyst_price_targets()
    earnings_estimates = _extract_earnings_estimates(yf_ticker.get_earnings_estimate())
    recommendations = _extract_recommendation_mix(yf_ticker.get_recommendations_summary())
    major_holders = _dict_from_dataframe(yf_ticker.get_major_holders())
    insider_roster = _records_from_dataframe(yf_ticker.get_insider_roster_holders(), limit=10)
    target_mean = analyst_targets.get("mean")
    target_median = analyst_targets.get("median")
    target_reference = target_median or target_mean
    target_upside = (target_reference / current_price) - 1

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
            "dayChangePercent": (current_price / info.get("previousClose")) - 1,
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
        },
        "analyst": {
            "targets": {k: _clean_value(analyst_targets.get(k)) for k in ["low", "high", "mean", "median"]},
            "targetUpside": _clean_value(target_upside),
            "recommendations": {"current": recommendations},
        },
        "eps": {
            "estimates": earnings_estimates,
        },
        "ownership": {
            "insidersPercentHeld": major_holders.get("insidersPercentHeld"),
            "institutionsPercentHeld": major_holders.get("institutionsPercentHeld"),
            "institutionsCount": major_holders.get("institutionsCount"),
            "insiderRoster": insider_roster,
        },
    }
