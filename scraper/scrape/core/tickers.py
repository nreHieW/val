import csv
from io import StringIO

from scrape.core.http_utils import request_get

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_EXCLUDED_NAME_FRAGMENTS = (
    " warrant",
    " warrants",
    " unit",
    " units",
    " right",
    " rights",
    " preferred",
    " preference",
    " depositary",
    " notes due",
    " senior notes",
    " subordinated notes",
    " bond",
    " debenture",
    " etf",
    " etn",
    " exchange-traded note",
    " fund",
    " trust",
    "acquisition",
    " blank check",
    " special purpose",
    " spac",
)
def _read_pipe_table(url):
    response = request_get(url, timeout=30)
    response.raise_for_status()
    lines = [line for line in response.text.splitlines() if line and not line.startswith("File Creation Time:")]
    return csv.DictReader(StringIO("\n".join(lines)), delimiter="|")


def _is_common_operating_stock(symbol, name, etf, test_issue):
    name = f" {name.lower()} "
    return not (
        not symbol
        or etf.upper() == "Y"
        or test_issue.upper() == "Y"
        or any(fragment in name for fragment in _EXCLUDED_NAME_FRAGMENTS)
        or any(char in symbol for char in ".$^")
    )


def get_all_tickers():
    tickers = []
    for row in _read_pipe_table(_NASDAQ_LISTED_URL):
        symbol = row.get("Symbol", "").strip()
        if row.get("Financial Status", "") != "D" and _is_common_operating_stock(
            symbol,
            row.get("Security Name", ""),
            row.get("ETF", ""),
            row.get("Test Issue", ""),
        ):
            tickers.append(symbol)

    for row in _read_pipe_table(_OTHER_LISTED_URL):
        symbol = row.get("ACT Symbol", "").strip()
        if _is_common_operating_stock(
            symbol,
            row.get("Security Name", ""),
            row.get("ETF", ""),
            row.get("Test Issue", ""),
        ):
            tickers.append(symbol)

    return sorted(set(tickers))
