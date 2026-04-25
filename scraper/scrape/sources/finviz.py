from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup

from scrape.core.http_utils import get_htmls


def parse_finviz(tickers):
    finviz_urls = ["https://finviz.com/quote.ashx?t=" + ticker for ticker in tickers]
    htmls = get_htmls(finviz_urls)
    perf_columns = ["Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y", "Perf Year", "Perf YTD"]
    dfs = []

    for i, html in enumerate(htmls):
        try:
            soup = BeautifulSoup(html, "lxml")
            table = soup.find("table", class_="snapshot-table2")
            if table:
                df = pd.read_html(StringIO(str(table)))[0].iloc[:, -2:].set_index(10)
                df[11] = df[11].astype(str).str.replace("%", "")
                perf_values = df.loc[perf_columns].astype(float).T.reset_index(drop=True)
                indiv = pd.DataFrame(perf_values, columns=perf_columns)
            else:
                raise ValueError("No table found for ticker: " + tickers[i])
            indiv["Ticker"] = tickers[i]
            dfs.append(indiv)
        except Exception as e:
            print("[ERROR] Failed to parse Finviz", tickers[i], e)

    return pd.concat(dfs, axis=0, ignore_index=True).set_index("Ticker")
