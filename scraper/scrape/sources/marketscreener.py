import datetime
import json
import logging
import os
import re
import threading
import time
from io import StringIO
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from scrape.core.config import (
    JSON_LOCK,
    MARKETSCREENER_JITTER_SECONDS,
    MARKETSCREENER_MAX_WORKERS,
    MARKETSCREENER_MIN_INTERVAL_SECONDS,
    MARKETSCREENER_RETRIES,
    MARKETSCREENER_RETRY_SLEEP_SECONDS,
)
from scrape.core.http_utils import browser_get, reset_browser_session
from scrape.core.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
_MARKETSCREENER_CACHE_FILE = "marketscreener_links.json"
_MARKETSCREENER_CACHE = {}
_MARKETSCREENER_CACHE_LOADED = False
_MARKETSCREENER_CACHE_DIRTY = False
_MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE = 0
_MARKETSCREENER_CACHE_SAVE_INTERVAL = 25
_MARKETSCREENER_IMPERSONATE = ("chrome124", "chrome120", "safari184")
_MARKETSCREENER_SEMAPHORE = threading.BoundedSemaphore(MARKETSCREENER_MAX_WORKERS)
_MARKETSCREENER_LIMITER = RateLimiter(MARKETSCREENER_MIN_INTERVAL_SECONDS, MARKETSCREENER_JITTER_SECONDS)
_MARKETSCREENER_STATS = {
    "cache_hits": 0,
    "cache_misses": 0,
    "requests": 0,
    "retries": 0,
    "limiter_wait_seconds": 0.0,
    "http_seconds": 0.0,
}
_MARKETSCREENER_STATS_LOCK = threading.Lock()


class MarketScreenerForecastUnavailable(ValueError):
    """Raised when MarketScreener exposes historical financials but no forecast page."""


def _increment_stat(name, amount=1):
    with _MARKETSCREENER_STATS_LOCK:
        _MARKETSCREENER_STATS[name] += amount


def log_marketscreener_stats():
    with _MARKETSCREENER_STATS_LOCK:
        stats = _MARKETSCREENER_STATS.copy()
    logger.info(
        "MarketScreener stats: %s cache hits, %s cache misses, %s requests, %s retries, %.1fs limiter wait, %.1fs HTTP",
        stats["cache_hits"],
        stats["cache_misses"],
        stats["requests"],
        stats["retries"],
        stats["limiter_wait_seconds"],
        stats["http_seconds"],
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
        logger.info("MarketScreener URL cache loaded: %s links", len(_MARKETSCREENER_CACHE))


def _save_marketscreener_cache_locked():
    global _MARKETSCREENER_CACHE_DIRTY, _MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE
    if not _MARKETSCREENER_CACHE_DIRTY:
        return
    temp_file = _MARKETSCREENER_CACHE_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(_MARKETSCREENER_CACHE, f)
    os.replace(temp_file, _MARKETSCREENER_CACHE_FILE)
    _MARKETSCREENER_CACHE_DIRTY = False
    _MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE = 0


def save_marketscreener_cache():
    with JSON_LOCK:
        _save_marketscreener_cache_locked()


def _raise_if_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise TimeoutError("MarketScreener request cancelled")


def _sleep_with_cancel(seconds, cancel_event):
    if cancel_event is None:
        time.sleep(seconds)
    elif cancel_event.wait(seconds):
        _raise_if_cancelled(cancel_event)


def _marketscreener_search(ticker, query, cancel_event=None):
    search_url = "https://www.marketscreener.com/search/?q=" + "+".join(query.split())
    page = _marketscreener_get(search_url, cancel_event)
    soup = BeautifulSoup(page.content, "lxml")
    for row in soup.find_all("tr"):
        ticker_tag = row.find("td", {"class": "txt-bold"})
        currency_tag = row.find("span", {"class": "txt-muted"})
        link_tag = row.find("a", href=True)
        if ticker_tag and currency_tag and link_tag:
            if ticker_tag.text.strip() == ticker and currency_tag.text.strip() == "USD":
                return "https://www.marketscreener.com" + link_tag["href"]
    return None


def get_marketscreener_url(ticker, name: str = "", cancel_event=None):
    global _MARKETSCREENER_CACHE_DIRTY, _MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE
    load_marketscreener_cache()
    with JSON_LOCK:
        cached_link = _MARKETSCREENER_CACHE.get(ticker)
    if cached_link:
        _increment_stat("cache_hits")
        return cached_link
    _increment_stat("cache_misses")

    queries = [ticker]
    if name:
        queries.append(name)

    found_link = None
    for query in queries:
        _raise_if_cancelled(cancel_event)
        found_link = _marketscreener_search(ticker, query, cancel_event)
        if found_link:
            break

    if not found_link:
        logger.debug("Could not find %s on marketscreener", ticker)
    else:
        with JSON_LOCK:
            _MARKETSCREENER_CACHE[ticker] = found_link
            _MARKETSCREENER_CACHE_DIRTY = True
            _MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE += 1
            if _MARKETSCREENER_CACHE_UPDATES_SINCE_SAVE >= _MARKETSCREENER_CACHE_SAVE_INTERVAL:
                _save_marketscreener_cache_locked()

    return found_link


def _marketscreener_get(url, cancel_event=None, validator=None):
    last_error = None
    for attempt in range(MARKETSCREENER_RETRIES):
        try:
            _raise_if_cancelled(cancel_event)
            limiter_started = time.monotonic()
            try:
                _MARKETSCREENER_LIMITER.wait(cancel_event)
            finally:
                _increment_stat("limiter_wait_seconds", time.monotonic() - limiter_started)
            _raise_if_cancelled(cancel_event)
            with _MARKETSCREENER_SEMAPHORE:
                _raise_if_cancelled(cancel_event)
                _increment_stat("requests")
                http_started = time.monotonic()
                try:
                    response = browser_get(
                        url,
                        impersonate=_MARKETSCREENER_IMPERSONATE[attempt % len(_MARKETSCREENER_IMPERSONATE)],
                    )
                finally:
                    _increment_stat("http_seconds", time.monotonic() - http_started)
            _raise_if_cancelled(cancel_event)
            response.raise_for_status()
            text = response.text.lower()
            if response.status_code in {403, 429, 503} or any(
                marker in text
                for marker in ("cf-chl", "g-recaptcha-response", "access denied", "too many requests")
            ):
                raise RuntimeError(f"MarketScreener anti-bot page returned for {url}")
            if validator is not None:
                validator(response)
            return response
        except Exception as e:
            last_error = e
            _raise_if_cancelled(cancel_event)
            if attempt < MARKETSCREENER_RETRIES - 1:
                _increment_stat("retries")
                reset_browser_session()
                _sleep_with_cancel(MARKETSCREENER_RETRY_SLEEP_SECONDS * (attempt + 1), cancel_event)
    raise last_error


def _marketscreener_number(value):
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float, np.number)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return 0.0

    multiplier = 1.0
    suffix = text[-1].upper()
    if suffix in {"T", "B", "M", "K"}:
        multiplier = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}[suffix]
        text = text[:-1]

    parsed = pd.to_numeric(text, errors="coerce")
    return (0.0 if pd.isna(parsed) else float(parsed)) * multiplier


def _clean_segment_label(value):
    text = BeautifulSoup(str(value).replace("<br>", " ").replace("<br/>", " "), "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def get_revenue_by_region(ticker, url, cancel_event=None):
    if not url:
        raise ValueError(f"No MarketScreener URL for {ticker}")

    page = _marketscreener_get(url.rstrip("/") + "/finances-segments/", cancel_event)
    soup = BeautifulSoup(page.content, "lxml")

    for header in soup.find_all("div", {"class": "card-header"}):
        if "geographical revenue distribution history" not in header.get_text(" ", strip=True).lower():
            continue
        card = header.find_parent(class_=lambda classes: classes and "card" in classes)
        chart = card.find(attrs={"data-fct-name": "drawFinancialSegmentCAChart"})
        revenues = {}
        for segment_key, segment in json.loads(chart["data-fct-attr"]).get("data", {}).items():
            segment_name = _clean_segment_label(segment.get("name") or segment_key)
            if segment_name.lower() == "unallocated":
                continue
            segment_value = 0.0
            for value in reversed(segment.get("data") or []):
                if pd.isna(value):
                    continue
                segment_value = _marketscreener_number(value)
                if np.isfinite(segment_value):
                    break
            if segment_name and segment_value > 0:
                revenues[segment_name] = segment_value
        if revenues:
            return revenues

    for header in soup.find_all("div", {"class": "card-header"}):
        if "geographical breakdown of sales" not in header.get_text(" ", strip=True).lower():
            continue
        card = header.find_parent("div", class_=lambda classes: classes and "card" in classes)
        table = card.find("table")
        df = pd.read_html(StringIO(str(table)))[0]
        label_col = df.columns[0]
        country_rows = [
            index
            for index, row in enumerate(table.find_all("tr")[1:])
            if "bg-grey-light" in row.get("class", [])
        ]
        year_columns = {}
        for column in df.columns[1:]:
            match = re.search(r"\b(20\d{2}|19\d{2})\b", str(column))
            if match:
                year_columns[int(match.group(1))] = column
        if not year_columns:
            raise ValueError(f"No geographical revenue year columns for {ticker}")

        for _, latest_col in sorted(year_columns.items(), reverse=True):
            revenues = {}
            for index in country_rows:
                segment_name = _clean_segment_label(df.iloc[index][label_col])
                segment_value = _marketscreener_number(df.iloc[index][latest_col])
                if segment_value > 0:
                    revenues[re.sub(r"\s+\d.*$", "", segment_name).strip()] = segment_value
            if revenues:
                return revenues

    raise ValueError(f"No geographical revenue segments for {ticker}")


def _forecast_income_statement_section(soup):
    for header in soup.select(".card-header"):
        if "income statement" not in header.get_text(" ", strip=True).lower():
            continue
        card = header.find_parent("div", class_=lambda classes: classes and "card" in classes)
        table = card.find("table") if card else None
        if table is not None:
            return card, table
    return None, None


def _is_forecast_page(url):
    return urlparse(str(url)).path.rstrip("/").endswith("/finances")


def _validate_revenue_forecast_page(response):
    if not _is_forecast_page(response.url):
        raise MarketScreenerForecastUnavailable(
            f"MarketScreener redirected forecast request to {str(response.url)!r}"
        )
    soup = BeautifulSoup(response.content, features="lxml")
    _, table = _forecast_income_statement_section(soup)
    if table is None:
        raise RuntimeError("MarketScreener forecast page missing income statement section")


def get_revenue_forecasts(url, cancel_event=None):
    request_url = url.rstrip("/") + "/finances/"
    page = _marketscreener_get(request_url, cancel_event, validator=_validate_revenue_forecast_page)

    soup = BeautifulSoup(page.content, features="lxml")
    card, table = _forecast_income_statement_section(soup)
    if table is not None:
        income_statement = pd.read_html(StringIO(str(table)))[0]
        income_statement = income_statement.dropna(axis=1, how="all")
        income_statement.iloc[:, 0] = income_statement.iloc[:, 0].str.replace(r"\d", "", regex=True)
        income_statement.set_index(income_statement.columns[0], inplace=True)
        income_statement.index = income_statement.index.str.strip()

        superscript = card.find("sup")
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

    raise RuntimeError(f"MarketScreener forecast page missing income statement section for URL {url!r}")
