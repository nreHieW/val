from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup

from scrape.core.http_utils import get_htmls

_PERF_COLUMNS = ["Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y", "Perf Year", "Perf YTD"]


def parse_finviz(tickers):
    finviz_urls = ["https://finviz.com/quote.ashx?t=" + t for t in tickers]
    htmls = get_htmls(finviz_urls, workers=10)
    dfs = []

    for i, ticker in enumerate(tickers):
        html = htmls[i]
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_="snapshot-table2")
        if not table:
            # raise ValueError("No table found for ticker: " + ticker)
            print(f"No table found for ticker: {ticker}")
            continue
        df = pd.read_html(StringIO(str(table)))[0].iloc[:, -2:].set_index(10)
        df[11] = df[11].astype(str).str.replace("%", "", regex=False).str.strip()
        perf_series = pd.to_numeric(df.loc[_PERF_COLUMNS][11], errors="coerce")
        perf_values = perf_series.to_frame().T.reset_index(drop=True)
        indiv = pd.DataFrame(perf_values, columns=_PERF_COLUMNS)
        indiv["Ticker"] = ticker
        dfs.append(indiv)
    return pd.concat(dfs, axis=0, ignore_index=True).set_index("Ticker")