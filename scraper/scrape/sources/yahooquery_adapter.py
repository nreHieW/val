import re
import pandas as pd
from yahooquery import Ticker


INFO_MODULES = [
    "summaryProfile",
    "summaryDetail",
    "financialData",
    "defaultKeyStatistics",
    "quoteType",
    "price",
    "earningsTrend",
    "recommendationTrend",
    "majorHoldersBreakdown",
    "insiderHolders",
]
_METADATA_COLUMNS = {"asOfDate", "periodType", "currencyCode"}
_TARGET_KEYS = {
    "low": "targetLowPrice",
    "high": "targetHighPrice",
    "mean": "targetMeanPrice",
    "median": "targetMedianPrice",
}


def _humanize_field(name: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def statement_to_wide_shape(df: pd.DataFrame, period_type: str, yahoo_symbol: str | None = None) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    statement = df.copy()
    if yahoo_symbol and isinstance(statement.index, pd.MultiIndex) and "symbol" in statement.index.names:
        statement = statement.xs(yahoo_symbol, level="symbol", drop_level=False)
    elif yahoo_symbol and statement.index.name == "symbol":
        statement = statement.loc[[yahoo_symbol]] if yahoo_symbol in statement.index else statement.iloc[0:0]
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


class YahooQueryTicker:
    def __init__(
        self,
        symbol: str,
        modules=None,
        quarterly_income_stmt=None,
        quarterly_balance_sheet=None,
        quarterly_cashflow=None,
        income_stmt=None,
        history=None,
    ):
        self.ticker = symbol
        self.yahoo_symbol = symbol.replace(".", "-")
        self._client = None
        self._modules = modules
        self._info = None
        self._quarterly_income_stmt = quarterly_income_stmt
        self._quarterly_balance_sheet = quarterly_balance_sheet
        self._quarterly_cashflow = quarterly_cashflow
        self._income_stmt = income_stmt
        self._history = history

    def _yq(self):
        if self._client is None:
            self._client = Ticker(self.yahoo_symbol, asynchronous=True)
        return self._client

    def _payload(self, payload, *, required=False):
        if not isinstance(payload, dict):
            if required:
                raise ValueError(f"Yahoo query returned invalid payload for {self.ticker}: {payload}")
            return {}

        if self.yahoo_symbol in payload:
            value = payload[self.yahoo_symbol]
        elif self.ticker in payload:
            value = payload[self.ticker]
        elif self.ticker.upper() in payload:
            value = payload[self.ticker.upper()]
        else:
            if required:
                raise ValueError(f"Yahoo query returned no payload for {self.ticker}")
            return {}

        if isinstance(value, dict) and value.get("error"):
            raise ValueError(f"Yahoo query failed for {self.ticker}: {value['error']}")
        if isinstance(value, str):
            if required or "quote not found" in value.lower():
                raise ValueError(f"Yahoo query failed for {self.ticker}: {value}")
            return {}
        return value or {}

    def _module(self, modules: dict, name: str, *, required=False) -> dict:
        value = modules.get(name, {})
        if isinstance(value, dict):
            return value
        if required or "quote not found" in str(value).lower():
            raise ValueError(f"Yahoo query failed for {self.ticker}: {value}")
        return {}

    def get_info(self) -> dict:
        if self._info is None:
            modules = self._modules if self._modules is not None else self._payload(self._yq().get_modules(INFO_MODULES), required=True)
            quote_type = self._module(modules, "quoteType", required=True)
            price = self._module(modules, "price", required=True)
            if quote_type.get("quoteType") == "NONE":
                raise ValueError(f"Yahoo query failed for {self.ticker}: quote not found")

            info = {
                **quote_type,
                **self._module(modules, "summaryProfile"),
                **self._module(modules, "summaryDetail"),
                **self._module(modules, "defaultKeyStatistics"),
                **self._module(modules, "financialData"),
                **price,
            }
            info["symbol"] = info.get("symbol") or self.yahoo_symbol
            info["currentPrice"] = info.get("currentPrice") or info.get("regularMarketPrice")
            info["previousClose"] = info.get("previousClose") or info.get("regularMarketPreviousClose")
            self._info = info
        return self._info

    @property
    def quarterly_income_stmt(self) -> pd.DataFrame:
        if self._quarterly_income_stmt is None:
            self._quarterly_income_stmt = statement_to_wide_shape(self._yq().income_statement(frequency="q"), "3M", self.yahoo_symbol)
        return self._quarterly_income_stmt

    @property
    def quarterly_balance_sheet(self) -> pd.DataFrame:
        if self._quarterly_balance_sheet is None:
            self._quarterly_balance_sheet = statement_to_wide_shape(self._yq().balance_sheet(frequency="q"), "3M", self.yahoo_symbol)
        return self._quarterly_balance_sheet

    @property
    def quarterly_cashflow(self) -> pd.DataFrame:
        if self._quarterly_cashflow is None:
            self._quarterly_cashflow = statement_to_wide_shape(self._yq().cash_flow(frequency="q"), "3M", self.yahoo_symbol)
        return self._quarterly_cashflow

    @property
    def income_stmt(self) -> pd.DataFrame:
        if self._income_stmt is None:
            self._income_stmt = statement_to_wide_shape(self._yq().income_statement(), "12M", self.yahoo_symbol)
        return self._income_stmt

    def history(self, *args, **kwargs) -> pd.DataFrame:
        if self._history is not None:
            return self._history
        try:
            return self._yq().history(*args, **kwargs)
        except KeyError as e:
            if str(e).strip("'") != self.yahoo_symbol:
                raise
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "adjclose"])

    def get_analyst_price_targets(self) -> dict:
        info = self.get_info()
        return {key: info.get(source_key) for key, source_key in _TARGET_KEYS.items()}

    def get_earnings_estimate(self) -> pd.DataFrame:
        if self._modules is not None:
            trend = self._module(self._modules, "earningsTrend").get("trend", [])
        else:
            trend = self._payload(self._yq().earnings_trend).get("trend", [])
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
        if self._modules is not None:
            return pd.DataFrame(self._module(self._modules, "recommendationTrend").get("trend", []))
        recommendations = self._yq().recommendation_trend
        return recommendations if isinstance(recommendations, pd.DataFrame) else pd.DataFrame()

    def get_major_holders(self) -> pd.DataFrame:
        if self._modules is not None:
            holders = self._module(self._modules, "majorHoldersBreakdown")
        else:
            holders = self._payload(self._yq().major_holders)
        return pd.DataFrame.from_dict(holders, orient="index", columns=["Value"])

    def get_insider_roster_holders(self) -> pd.DataFrame:
        if self._modules is not None:
            return pd.DataFrame(self._module(self._modules, "insiderHolders").get("holders", []))
        holders = self._yq().insider_holders
        return holders if isinstance(holders, pd.DataFrame) else pd.DataFrame()


def yahooquery_close_series(history: pd.DataFrame) -> pd.Series:
    if history is None or history.empty:
        return pd.Series(dtype="float64")
    close = history["close"] if "close" in history.columns else history["Close"]
    close = close.dropna()
    if isinstance(close.index, pd.MultiIndex):
        close = close.droplevel(0)
    close.index = pd.to_datetime(close.index, utc=True).tz_localize(None)
    return close
