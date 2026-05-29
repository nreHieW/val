import re
from functools import lru_cache

import pandas as pd
from yahooquery import Ticker


_METADATA_COLUMNS = {"asOfDate", "periodType", "currencyCode"}
_TARGET_KEYS = {
    "low": "targetLowPrice",
    "high": "targetHighPrice",
    "mean": "targetMeanPrice",
    "median": "targetMedianPrice",
}


def _get_symbol_payload(payload, symbol: str):
    if not isinstance(payload, dict):
        return payload
    if symbol in payload:
        value = payload[symbol]
    elif symbol.upper() in payload:
        value = payload[symbol.upper()]
    else:
        raise ValueError(f"Yahoo query returned no payload for {symbol}")
    if isinstance(value, dict) and value.get("error"):
        raise ValueError(f"Yahoo query failed for {symbol}: {value['error']}")
    return value or {}


def _humanize_field(name: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def _statement_to_wide_shape(df: pd.DataFrame, period_type: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    statement = df.copy()
    if "periodType" in statement.columns:
        statement = statement[statement["periodType"] == period_type]
    if statement.empty:
        return pd.DataFrame()

    statement["asOfDate"] = pd.to_datetime(statement["asOfDate"])
    statement = statement.sort_values("asOfDate", ascending=False).drop_duplicates("asOfDate")
    statement = statement.set_index("asOfDate")
    value_columns = [column for column in statement.columns if column not in _METADATA_COLUMNS]
    statement = statement[value_columns].rename(columns=_humanize_field)
    return statement.T


@lru_cache(maxsize=10000)
def get_yahooquery_info(symbol: str) -> dict:
    return YahooQueryTicker(symbol).get_info()


class YahooQueryTicker:
    def __init__(self, symbol: str):
        self.ticker = symbol
        self._client = Ticker(symbol)
        self._info = None

    def get_info(self) -> dict:
        if self._info is None:
            profile = _get_symbol_payload(self._client.summary_profile, self.ticker)
            detail = _get_symbol_payload(self._client.summary_detail, self.ticker)
            financial = _get_symbol_payload(self._client.financial_data, self.ticker)
            key_stats = _get_symbol_payload(self._client.key_stats, self.ticker)
            quote_type = _get_symbol_payload(self._client.quote_type, self.ticker)
            price = _get_symbol_payload(self._client.price, self.ticker)

            info = {**quote_type, **profile, **detail, **key_stats, **financial, **price}
            info["symbol"] = info.get("symbol") or self.ticker
            info["currentPrice"] = info.get("currentPrice") or info.get("regularMarketPrice")
            info["previousClose"] = info.get("previousClose") or info.get("regularMarketPreviousClose")
            self._info = info
        return self._info

    @property
    def quarterly_income_stmt(self) -> pd.DataFrame:
        return _statement_to_wide_shape(self._client.income_statement(frequency="q"), "3M")

    @property
    def quarterly_balance_sheet(self) -> pd.DataFrame:
        return _statement_to_wide_shape(self._client.balance_sheet(frequency="q"), "3M")

    @property
    def quarterly_cashflow(self) -> pd.DataFrame:
        return _statement_to_wide_shape(self._client.cash_flow(frequency="q"), "3M")

    @property
    def income_stmt(self) -> pd.DataFrame:
        return _statement_to_wide_shape(self._client.income_statement(), "12M")

    def history(self, *args, **kwargs) -> pd.DataFrame:
        return self._client.history(*args, **kwargs)

    def get_analyst_price_targets(self) -> dict:
        financial = _get_symbol_payload(self._client.financial_data, self.ticker)
        return {key: financial.get(source_key) for key, source_key in _TARGET_KEYS.items()}

    def get_earnings_estimate(self) -> pd.DataFrame:
        trend = _get_symbol_payload(self._client.earnings_trend, self.ticker).get("trend", [])
        records = []
        for row in trend:
            estimate = row.get("earningsEstimate") or {}
            records.append(
                {
                    "period": row.get("period"),
                    "avg": estimate.get("avg"),
                    "low": estimate.get("low"),
                    "high": estimate.get("high"),
                    "yearAgoEps": estimate.get("yearAgoEps"),
                    "numberOfAnalysts": estimate.get("numberOfAnalysts"),
                    "growth": estimate.get("growth"),
                }
            )
        return pd.DataFrame(records)

    def get_recommendations_summary(self) -> pd.DataFrame:
        recommendations = self._client.recommendation_trend
        return recommendations if isinstance(recommendations, pd.DataFrame) else pd.DataFrame()

    def get_major_holders(self) -> pd.DataFrame:
        holders = _get_symbol_payload(self._client.major_holders, self.ticker)
        return pd.DataFrame.from_dict(holders, orient="index", columns=["Value"])

    def get_insider_roster_holders(self) -> pd.DataFrame:
        holders = self._client.insider_holders
        return holders if isinstance(holders, pd.DataFrame) else pd.DataFrame()


def yahooquery_close_series(history: pd.DataFrame) -> pd.Series:
    if history is None or history.empty:
        return pd.Series(dtype="float64")
    close = history["close"] if "close" in history.columns else history["Close"]
    close = close.dropna()
    if isinstance(close.index, pd.MultiIndex):
        close = close.droplevel(0)
    close.index = pd.to_datetime(close.index)
    return close
