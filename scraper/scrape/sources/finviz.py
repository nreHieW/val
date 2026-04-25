import time
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup

from scrape.core.config import FINVIZ_RETRIES, FINVIZ_RETRY_SLEEP_SECONDS
from scrape.core.http_utils import fetch_html, get_htmls

_PERF_COLUMNS = ["Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y", "Perf Year", "Perf YTD"]


def _parse_finviz_html(html: str, ticker: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="snapshot-table2")
    if not table:
        raise ValueError("No table found for ticker: " + ticker)
    df = pd.read_html(StringIO(str(table)))[0].iloc[:, -2:].set_index(10)
    df[11] = df[11].astype(str).str.replace("%", "")
    perf_values = df.loc[_PERF_COLUMNS].astype(float).T.reset_index(drop=True)
    indiv = pd.DataFrame(perf_values, columns=_PERF_COLUMNS)
    indiv["Ticker"] = ticker
    return indiv


def parse_finviz(tickers):
    finviz_urls = ["https://finviz.com/quote.ashx?t=" + t for t in tickers]
    url_by_ticker = dict(zip(tickers, finviz_urls))
    htmls = get_htmls(finviz_urls)
    dfs = []

    for i, ticker in enumerate(tickers):
        url = url_by_ticker[ticker]
        last_exc: Exception | None = None
        for attempt in range(FINVIZ_RETRIES):
            html = htmls[i] if attempt == 0 else fetch_html(url)
            try:
                dfs.append(_parse_finviz_html(html, ticker))
                break
            except Exception as e:
                last_exc = e
                if attempt < FINVIZ_RETRIES - 1:
                    time.sleep(FINVIZ_RETRY_SLEEP_SECONDS * (attempt + 1))
                else:
                    print(f"[ERROR] Failed to parse Finviz {ticker} after {FINVIZ_RETRIES} attempts: {last_exc!r}")

    return pd.concat(dfs, axis=0, ignore_index=True).set_index("Ticker")
