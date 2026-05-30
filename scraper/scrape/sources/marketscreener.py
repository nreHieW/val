import datetime
import json
import logging
import os
import re
import time
from io import StringIO

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from scrape.core.config import (
    JSON_LOCK,
    MARKETSCREENER_JITTER_SECONDS,
    MARKETSCREENER_MIN_INTERVAL_SECONDS,
    MARKETSCREENER_RETRIES,
    MARKETSCREENER_RETRY_SLEEP_SECONDS,
)
from scrape.core.http_utils import browser_get
from scrape.core.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
_MARKETSCREENER_CACHE_FILE = "marketscreener_links.json"
_MARKETSCREENER_CACHE = {}
_MARKETSCREENER_CACHE_LOADED = False
_MARKETSCREENER_CACHE_DIRTY = False
_MARKETSCREENER_RATE_LIMITER = RateLimiter(
    MARKETSCREENER_MIN_INTERVAL_SECONDS,
    MARKETSCREENER_JITTER_SECONDS,
)


def load_marketscreener_cache():
    global _MARKETSCREENER_CACHE, _MARKETSCREENER_CACHE_LOADED
    with JSON_LOCK:
        if _MARKETSCREENER_CACHE_LOADED:
            return
        if os.path.exists(_MARKETSCREENER_CACHE_FILE):
            with open(_MARKETSCREENER_CACHE_FILE, "r") as f:
                _MARKETSCREENER_CACHE = json.load(f)
        _MARKETSCREENER_CACHE_LOADED = True


def save_marketscreener_cache():
    global _MARKETSCREENER_CACHE_DIRTY
    with JSON_LOCK:
        if not _MARKETSCREENER_CACHE_DIRTY:
            return
        with open(_MARKETSCREENER_CACHE_FILE, "w") as f:
            json.dump(_MARKETSCREENER_CACHE, f)
        _MARKETSCREENER_CACHE_DIRTY = False


def get_marketscreener_url(ticker, name: str = ""):
    global _MARKETSCREENER_CACHE_DIRTY
    load_marketscreener_cache()
    with JSON_LOCK:
        cached_link = _MARKETSCREENER_CACHE.get(ticker)
    if cached_link:
        return cached_link

    search_url = "https://www.marketscreener.com/search/?q=" + "+".join(ticker.split())
    page = _marketscreener_get(search_url)
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
        page = _marketscreener_get(search_url)
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
        logger.debug("Could not find %s on marketscreener", ticker)
    else:
        with JSON_LOCK:
            _MARKETSCREENER_CACHE[ticker] = found_link
            _MARKETSCREENER_CACHE_DIRTY = True

    return found_link


def _marketscreener_get(url):
    last_error = None
    for attempt in range(MARKETSCREENER_RETRIES):
        try:
            _MARKETSCREENER_RATE_LIMITER.wait()
            response = browser_get(url)
            response.raise_for_status()
            text = response.text.lower()
            if response.status_code in {403, 429, 503} or any(
                marker in text
                for marker in ("cf-chl", "g-recaptcha-response", "access denied", "too many requests")
            ):
                raise RuntimeError(f"MarketScreener anti-bot page returned for {url}")
            return response
        except Exception as e:
            last_error = e
            if attempt < MARKETSCREENER_RETRIES - 1:
                time.sleep(MARKETSCREENER_RETRY_SLEEP_SECONDS * (attempt + 1))
    raise last_error


def get_revenue_by_region(ticker, url):
    if not url:
        raise ValueError(f"No MarketScreener URL for {ticker}")
    page = _marketscreener_get(url + "company/")
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
    page = _marketscreener_get(url + "finances/")
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
            revenue_growth_rate_next_year = float(growth.values[0][1]) if growth.shape[1] > 1 and pd.notna(growth.values[0][1]) else 0
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
