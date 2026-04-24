import concurrent.futures
import datetime
import json
import os
import re
from io import StringIO

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrape.core.config import JSON_LOCK, MAX_WORKERS, REQUEST_TIMEOUT_SECONDS, headers
from scrape.core.http_utils import get_htmls


def get_marketscreener_url(ticker, name: str = ""):
    search_url = "https://www.marketscreener.com/search/?q=" + "+".join(ticker.split())
    page = requests.get(search_url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    soup = BeautifulSoup(page.content, "lxml")
    rows = soup.find_all("tr")
    found_link = None
    for row in rows:
        currency_tag = row.find("span", {"class": "txt-muted"})
        if currency_tag:
            currency = currency_tag.text.strip()
            if currency == "USD" and row.find("td", {"class": "txt-bold"}).text.strip() == ticker:
                link = row.find("a", href=True)["href"]
                found_link = "https://www.marketscreener.com" + link
                break

    if not found_link and name:
        search_url = "https://www.marketscreener.com/search/?q=" + "+".join(name.split())
        page = requests.get(search_url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        soup = BeautifulSoup(page.content, "lxml")
        rows = soup.find_all("tr")
        for row in rows:
            currency_tag = row.find("span", {"class": "txt-muted"})
            if currency_tag:
                currency = currency_tag.text.strip()
                if currency == "USD" and row.find("td", {"class": "txt-bold"}).text.strip() == ticker:
                    link = row.find("a", href=True)["href"]
                    found_link = "https://www.marketscreener.com" + link
                    break
    if not found_link:
        raise ValueError(f"Could not find {ticker} on marketscreener")

    with JSON_LOCK:
        if os.path.exists("marketscreener_links.json"):
            with open("marketscreener_links.json", "r") as f:
                data = json.load(f)
            data[ticker] = found_link
        else:
            data = {ticker: found_link}

        with open("marketscreener_links.json", "w") as f:
            json.dump(data, f)

    return found_link


def get_revenue_by_region(ticker, url):
    page = requests.get(url + "company/", headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    soup = BeautifulSoup(page.content, "lxml")
    df = None
    for div in soup.find_all("div", {"class": "card mb-15 card--collapsible card--scrollable"}):
        header_text = div.find("div", {"class": "card-header"}).text
        if header_text == "Sales per region":
            df = pd.read_html(str(div.find("table")))[0]
            break
    if df is None:
        raise ValueError(f"No sales per region table for {ticker}")
    countries = df[df.columns[0]].values
    countries = [re.search(r"^([^\d]+)", item).group(0).strip() for item in countries]
    df["country"] = countries
    df.set_index("country", inplace=True)
    numeric_col_names = [x for x in df.columns if x.isdigit()]
    latest_year = max([int(x) for x in numeric_col_names])
    df = df[numeric_col_names]
    return df[str(latest_year)].to_dict()


def get_revenue_forecasts(url):
    page = requests.get(url + "finances/", headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    soup = BeautifulSoup(page.content, features="lxml")
    for div in soup.find_all("div", {"class": "card card--collapsible mb-15"}):
        header = div.find("div", {"class": "card-header"})
        if not header:
            continue
        header_text = header.text.lower()
        if "income statement" in header_text:
            income_statement = pd.read_html(StringIO(str(div.find("table"))))[0]
            income_statement = income_statement.dropna(axis=1, how="all")
            income_statement.iloc[:, 0] = income_statement.iloc[:, 0].str.replace(r"\d", "", regex=True)
            income_statement.set_index(income_statement.columns[0], inplace=True)
            income_statement.index = income_statement.index.str.strip()

            superscript = div.find("sup")
            currency = ""
            unit = ""
            if superscript and superscript.attrs.get("title"):
                title = superscript.attrs["title"].strip().split()
                currency = title[0] if len(title) > 0 else ""
                unit = title[-1] if len(title) > 1 else ""

            unit_multiplier = {
                "trillion": 1e12,
                "billion": 1e9,
                "million": 1e6,
                "thousand": 1e3,
            }.get(unit.lower(), 1)

            indiv = income_statement.loc[["Net sales"]].apply(
                lambda column: pd.to_numeric(column.astype(str).str.replace(",", ""), errors="coerce")
            )
            curr_year = datetime.datetime.now().year - 1
            if str(curr_year) not in indiv.columns:
                raise ValueError(f"Income statement missing required net sales year column {str(curr_year)!r}")

            curr_year_index = indiv.columns.get_loc(str(curr_year))
            indiv = indiv.iloc[:, curr_year_index:].astype(float)
            consensus_revenues = {
                str(column): float(value) * unit_multiplier
                for column, value in indiv.iloc[0].items()
                if pd.notna(value)
            }
            growth = indiv.pct_change(axis=1)
            revenue_growth_rate_next_year = growth.values[0][1] if growth.shape[1] > 1 and pd.notna(growth.values[0][1]) else 0
            raw_compounded_growth_rates = [value for value in growth.values[0][1:] if pd.notna(value)]
            compounded_annual_revenue_growth_rate = float(np.mean(raw_compounded_growth_rates)) if raw_compounded_growth_rates else 0
            ebit = pd.Series(dtype=float)
            if "EBIT" in income_statement.index:
                ebit = income_statement.loc["EBIT", indiv.columns].apply(
                    lambda x: pd.to_numeric(str(x).replace(",", ""), errors="coerce")
                )
            consensus_ebit = {
                str(column): float(value) * unit_multiplier
                for column, value in ebit.items()
                if pd.notna(value)
            }

            op_margins = ebit / indiv if not ebit.empty else pd.DataFrame()
            op_margin_next_year = (
                op_margins[[str(curr_year + 2)]].iloc[0].values[0]
                if not op_margins.empty and str(curr_year + 2) in op_margins.columns
                else 0
            )  # MarketScreener has some inconsistencies of EBIT values versus yahoo finance
            return {
                "revenue_growth_rate_next_year": revenue_growth_rate_next_year,
                "compounded_annual_revenue_growth_rate": compounded_annual_revenue_growth_rate,
                "operating_margin_next_year": 0 if pd.isna(op_margin_next_year) else float(op_margin_next_year),
                "consensus_revenues": consensus_revenues,
                "consensus_ebit": consensus_ebit,
                "currency": currency,
                "unit": unit,
            }

    raise ValueError(f"No income statement section found for MarketScreener URL {url!r}")


def get_marketscreener_links(tickers):
    links = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_marketscreener_url, ticker): ticker for ticker in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            link = future.result()
            if not link.endswith("/"):
                link += "/"
            links[ticker] = link + "finances/"

    return links


def parse_marketscreener(marketscreener_urls):
    if not marketscreener_urls:
        return pd.DataFrame()

    htmls = get_htmls(list(marketscreener_urls.values()))
    htmls = dict(zip(marketscreener_urls.keys(), htmls))
    dfs = []

    for ticker, html in htmls.items():
        if not html:
            raise ValueError(f"Empty MarketScreener HTML for {ticker}")
        soup = BeautifulSoup(html, features="lxml")
        for div in soup.find_all("div", {"class": "card card--collapsible mb-15"}):
            header = div.find("div", {"class": "card-header"})
            if not header:
                continue
            header_text = header.text.lower()
            if "income statement" not in header_text:
                continue

            income_statement = pd.read_html(StringIO(str(div.find("table"))))[0]
            income_statement = income_statement.dropna(axis=1, how="all")
            first_col = income_statement.columns[0]
            income_statement[first_col] = income_statement[first_col].astype(str).str.replace(r"\d", "", regex=True).str.strip()
            income_statement.set_index(first_col, inplace=True)
            income_statement.index = income_statement.index.str.strip()
            if income_statement.index.has_duplicates:
                income_statement = income_statement.groupby(level=0).first()
            income_statement = income_statement.reindex(["Net sales", "Net income", "EBITDA", "EBIT"]).fillna(0)
            indiv = income_statement.stack()
            indiv.index = [" ".join(x) for x in indiv.index]
            indiv = indiv.to_frame().T

            superscript = div.find("sup")
            if superscript and superscript.attrs.get("title"):
                title = superscript.attrs["title"].strip().split()
                indiv["Currency"] = title[0] if len(title) > 0 else 0
                indiv["Unit"] = title[-1] if len(title) > 1 else 0
            else:
                indiv["Currency"] = 0
                indiv["Unit"] = 0

            indiv["Ticker"] = ticker
            dfs.append(indiv)
            break
        else:
            raise ValueError(f"No income statement found in MarketScreener HTML for {ticker}")

    if not dfs:
        return pd.DataFrame()

    marketscreener = pd.concat(dfs, axis=0, join="outer", ignore_index=True)
    return marketscreener.reset_index(drop=True).set_index("Ticker")
