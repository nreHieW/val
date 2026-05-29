import logging
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup

from scrape.core.http_utils import get_htmls

logger = logging.getLogger(__name__)

_PERF_COLUMNS = ["Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y", "Perf Year", "Perf YTD"]


def parse_finviz(tickers):
    finviz_urls = ["https://finviz.com/quote.ashx?t=" + t for t in tickers]
    htmls = get_htmls(finviz_urls, workers=2)
    dfs = []

    for ticker, html in zip(tickers, htmls):
        try:
            soup = BeautifulSoup(html, "lxml")
            table = soup.find("table", class_="snapshot-table2")
            if not table:
                logger.debug("No Finviz snapshot table found for %s", ticker)
                continue
            df = pd.read_html(StringIO(str(table)))[0].iloc[:, -2:].set_index(10)
            if not any(column in df.index for column in _PERF_COLUMNS):
                logger.debug("No Finviz performance columns found for %s", ticker)
                continue
            df[11] = df[11].astype(str).str.replace("%", "", regex=False).str.strip()
            perf_series = pd.to_numeric(df.reindex(_PERF_COLUMNS)[11], errors="coerce")
            perf_values = perf_series.to_frame().T.reset_index(drop=True)
            indiv = pd.DataFrame(perf_values, columns=_PERF_COLUMNS)
            indiv["Ticker"] = ticker
            dfs.append(indiv)
        except Exception as e:
            logger.debug("Failed to parse Finviz %s: %s", ticker, e)

    if not dfs:
        return pd.DataFrame(columns=_PERF_COLUMNS).rename_axis("Ticker")
    return pd.concat(dfs, axis=0, ignore_index=True).set_index("Ticker")
