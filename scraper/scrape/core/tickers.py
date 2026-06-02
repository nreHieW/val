import csv
import re
from io import StringIO

from scrape.core.config import REQUEST_TIMEOUT_SECONDS
from scrape.core.http_utils import request_get

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_EXCLUDED_SECURITY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwarrants?\b",
        r"\brights?\b",
        r"\bpreferred\b|\bpreference\b",
        r"\bnotes?\s+due\b|\bsenior notes?\b|\bsubordinated notes?\b|\bdebentures?\b",
        r"\bbonds\b|\bbond (?:fund|trust)\b",
        r"\betfs?\b|\betns?\b|\bexchange[- ]traded\b|\bfunds?\b",
        r"acquisitions?|\bblank check\b|\bspecial purpose\b|\bspacs?\b",
        r"\bsynthetic fixed-income\b|\bstrats\b|\bcorts\b|\bstructured repackaged\b|\bcapital trust\b",
    )
)
_TEMPORARY_SECURITY_PATTERN = re.compile(r"\bwhen[- ]issued\b|\bwhen[- ]distributed\b", re.IGNORECASE)
_UNIT_PATTERN = re.compile(r"\bunits?\b", re.IGNORECASE)
_ALLOWED_UNIT_PATTERN = re.compile(
    r"\bcommon units? representing limited partnership interests?\b"
    r"|\bdepositary units? representing limited partner interests?\b",
    re.IGNORECASE,
)
_DEPOSITARY_PATTERN = re.compile(r"\bdepositary\b", re.IGNORECASE)
_ALLOWED_DEPOSITARY_PATTERN = re.compile(
    r"\b(?:american|global) depositary\b"
    r"|\bdepositary units? representing limited partner interests?\b",
    re.IGNORECASE,
)
_PASSIVE_TRUST_PATTERN = re.compile(
    r"\b(?:allocation|dividend|duration|equity|global|gold|health sciences?|income|investors?|"
    r"micro-cap|multi-media|municipal|multimarket|natural resources?|opportunit(?:y|ies)|resources?|"
    r"science and technology|small-cap|technology|term|universal|utility|wellness)\b.*\btrust\b"
    r"|\btrust\b.*\b(?:income|investment grade|municipal|opportunit(?:y|ies)|term)\b",
    re.IGNORECASE,
)
_OPERATING_TRUST_PATTERN = re.compile(
    r"\b(?:digital infrastructure|finance|hospitality|lodging|mortgage|properties|"
    r"property|real estate|realty|storage affiliates)\b.*\btrust\b"
    r"|\bhealthcare trust\b|\breit\b|\broyalty trust\b|\btrust bancorp\b|\btrustco\b|\btrustmark\b"
    r"|\bnorthern trust corporation\b",
    re.IGNORECASE,
)


def _read_pipe_table(url):
    response = request_get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    lines = [line for line in response.text.splitlines() if line and not line.startswith("File Creation Time:")]
    return csv.DictReader(StringIO("\n".join(lines)), delimiter="|")


def _is_common_operating_stock(symbol, name, etf, test_issue):
    name = " ".join(name.split())
    return not (
        not symbol
        or etf.upper() == "Y"
        or test_issue.upper() == "Y"
        or any(char in symbol for char in "$^")
        or any(pattern.search(name) for pattern in _EXCLUDED_SECURITY_PATTERNS)
        or (symbol.endswith(".V") and _TEMPORARY_SECURITY_PATTERN.search(name))
        or (_UNIT_PATTERN.search(name) and not _ALLOWED_UNIT_PATTERN.search(name))
        or (_DEPOSITARY_PATTERN.search(name) and not _ALLOWED_DEPOSITARY_PATTERN.search(name))
        or (_PASSIVE_TRUST_PATTERN.search(name) and not _OPERATING_TRUST_PATTERN.search(name))
    )


def get_all_tickers():
    tickers = []
    for url, symbol_column in ((_NASDAQ_LISTED_URL, "Symbol"), (_OTHER_LISTED_URL, "ACT Symbol")):
        for row in _read_pipe_table(url):
            symbol = row.get(symbol_column, "").strip()
            if _is_common_operating_stock(
                symbol,
                row.get("Security Name", ""),
                row.get("ETF", ""),
                row.get("Test Issue", ""),
            ):
                tickers.append(symbol)

    return sorted(set(tickers))
