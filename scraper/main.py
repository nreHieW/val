import pandas as pd
import numpy as np
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import requests
import re
from bs4 import BeautifulSoup
import warnings
import datetime
from sentence_transformers import SentenceTransformer
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import os
import json
import concurrent.futures
import time
import threading
from io import StringIO

JSON_LOCK = threading.Lock()

load_dotenv()

warnings.filterwarnings("ignore")

headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"}

MAX_WORKERS = 120
YAHOO_INFO_MAX_WORKERS = int(os.getenv("YAHOO_INFO_MAX_WORKERS", "8"))
YAHOO_INFO_RETRIES = int(os.getenv("YAHOO_INFO_RETRIES", "4"))
YAHOO_INFO_RETRY_SLEEP_SECONDS = float(os.getenv("YAHOO_INFO_RETRY_SLEEP_SECONDS", "5"))
REQUEST_TIMEOUT_SECONDS = 30
TICKER_TIMEOUT_SECONDS = int(os.getenv("TICKER_TIMEOUT_SECONDS", "300"))
CURRENCIES = {
    "ARS",
    "AUD",
    "BRL",
    "CAD",
    "CHF",
    "CLP",
    "CNY",
    "COP",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "IDR",
    "ILS",
    "INR",
    "JPY",
    "KRW",
    "KZT",
    "MXN",
    "MYR",
    "PEN",
    "PHP",
    "SEK",
    "SGD",
    "TRY",
    "TWD",
    "USD",
    "VND",
    "ZAR",
}


def setup_proxies():
    response = requests.get(
        "https://www.sslproxies.org/",
        headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    proxies = []
    soup = BeautifulSoup(response.text, "html.parser")
    for row in soup.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) == 0:
            continue
        proxies.append({"ip": tds[0].string, "port": tds[1].string})
    proxies = [f"{x['ip']}:{x['port']}" for x in proxies if x["ip"] and x["port"]]
    proxies = [x for x in proxies if "-" not in x]  # remove date
    proxies = [x for x in proxies if len(x.split(":")) == 2 and len(x.split(".")) == 4]
    return proxies


PROXIES = setup_proxies()


def get_proxy():
    if len(PROXIES) == 0:
        return None
    idx = np.random.randint(0, len(PROXIES))
    return {"http": PROXIES[idx], "https": PROXIES[idx]}


def fetch_html(url, retries=2, sleep_seconds=10, use_proxy=False):
    for attempt in range(retries):
        try:
            proxies = get_proxy() if use_proxy else None
            return requests.get(url, headers=headers, proxies=proxies, timeout=REQUEST_TIMEOUT_SECONDS).text
        except Exception:
            if attempt < retries - 1:
                time.sleep(sleep_seconds)
    return ""


def get_htmls(urls, use_proxy=False, workers=MAX_WORKERS):
    html_responses = []
    for i in range(0, len(urls), workers):
        batch = urls[i : i + workers]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(batch))) as executor:
            batch_htmls = list(executor.map(lambda u: fetch_html(u, use_proxy=use_proxy), batch))
            html_responses.extend(batch_htmls)
        time.sleep(1)
    return html_responses


def run_with_timeout(func, timeout_seconds, *args, **kwargs):
    result = {}
    error = {}

    def target():
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as e:
            error["value"] = e

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout_seconds)

    if worker.is_alive():
        raise TimeoutError(f"Timed out after {timeout_seconds} seconds")
    if "value" in error:
        raise error["value"]
    return result.get("value")


def get_all_tickers():
    url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
    response = requests.get(url, timeout=30)
    return [ticker for ticker in response.text.split("\n") if ticker]


def get_mongo_client():
    uri = f"mongodb+srv://{os.getenv('MONGODB_USERNAME')}:{os.getenv('MONGODB_DB_PASSWORD')}@{os.getenv('MONGODB_DB_NAME')}.kdnx4hj.mongodb.net/?retryWrites=true&w=majority&appName={os.getenv('MONGODB_DB_NAME')}"
    return MongoClient(uri, server_api=ServerApi("1"))


# https://stackoverflow.com/questions/30098263/inserting-a-document-with-pymongo-invaliddocument-cannot-encode-object
class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(CustomEncoder, self).default(obj)


class StringMapper:
    def __init__(self, gts: list, threshold=0):
        self.model = SentenceTransformer("Alibaba-NLP/gte-base-en-v1.5", trust_remote_code=True)
        self.gts = gts
        self.embeddings = self.model.encode(gts)
        self.embeddings = self.embeddings / np.linalg.norm(self.embeddings, axis=1)[:, None]
        self.threshold = threshold

    def get_closest(self, query: str, num_results=1):
        if query in self.gts or query.lower() in self.gts:
            return [query]

        query_words = set(query.lower().split())
        candidates = []
        for gt in self.gts:
            gt_words = set(gt.lower().split())
            if any(len(word) >= 3 for word in query_words & gt_words):
                candidates.append(gt)
        if candidates:
            candidates = sorted(candidates, key=lambda x: len(x.split()))
            return [candidates[0]]

        query_embedding = self.model.encode(query)
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        similarities = np.dot(self.embeddings, query_embedding)
        indices = np.argsort(-similarities)
        indices = [i for i in indices if similarities[i] > self.threshold][:num_results]
        return [self.gts[i] for i in indices]

    def get_closest_with_scores(self, query: str, num_results=1, indices_to_adjust=None):
        if query in self.gts or query.lower() in self.gts:
            return [(query, 1.0)]

        query_words = set(query.lower().split())
        candidates = []
        for gt in self.gts:
            gt_words = set(gt.lower().split())
            if any(len(word) >= 3 for word in query_words & gt_words):
                candidates.append(gt)
        if candidates:
            candidates = sorted(candidates, key=lambda x: len(x.split()))
            return [(candidates[0], 1.0)]

        query_embedding = self.model.encode(query)
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        scores = np.dot(self.embeddings, query_embedding)
        if indices_to_adjust:
            scores[indices_to_adjust] += np.max(scores) * 0.1

        indices = np.argsort(-scores)
        indices = [i for i in indices if scores[i] > self.threshold][:num_results]
        return [(self.gts[i], scores[i]) for i in indices]


def get_exchange_rates():
    fx_rate = {}
    for currency in CURRENCIES:
        fx_rate[currency] = yf.Ticker(currency + "USD=X").history().Close.iloc[-1].item()
    return fx_rate


def get_regional_crps(revenues_by_region: dict, mapper: StringMapper, country_erps: dict):
    regions = list(revenues_by_region.keys())
    indices_to_adjust = [i for i in range(len(mapper.gts) - 10, len(mapper.gts))]
    mappings = [mapper.get_closest_with_scores(x, indices_to_adjust=indices_to_adjust) for x in regions]

    flattened_mappings = [(region, gt, score) for region, mapping in zip(regions, mappings) if mapping for gt, score in mapping]
    flattened_mappings.sort(key=lambda x: x[2], reverse=True)
    used_gts = set()
    final_mappings = {}

    for region, gt, score in flattened_mappings:
        if gt not in used_gts:
            final_mappings[region] = gt
            used_gts.add(gt)
    for region in regions:
        if region not in final_mappings:
            final_mappings[region] = "Global"
    # print(mapper.gts)
    crps = [country_erps[final_mappings[region]] for region in regions]
    total_revenues = sum(revenues_by_region.values())
    weights = [revenues_by_region[region] / total_revenues for region in regions]
    # print(final_mappings)
    return sum([x * y for x, y in zip(crps, weights)]), {final_mappings[region]: v for region, v in revenues_by_region.items()}


def get_industry_beta(industry: str, sector: str, mapper: StringMapper, industry_betas: dict):
    industry_result, industry_score = mapper.get_closest_with_scores(industry)[0]
    sector_result, sector_score = mapper.get_closest_with_scores(sector)[0]
    if (industry_score is None) and (sector_score is None):
        industry_result = "Grand Total"
        return industry_betas[industry_result], industry_result

    if industry_score > sector_score:
        return industry_betas[industry_result], industry_result
    else:
        return industry_betas[sector_result], sector_result


def get_10year_tbill():
    url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=US10Y&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1"
    res = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS).json()
    raw = res['FormattedQuoteResult']['FormattedQuote'][0]['last']
    res = raw.replace("%", "")
    return float(res) / 100


def get_mature_erp():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
    return pd.read_excel(url)["ERP (T12m)"].iloc[-1]


def synthetic_rating(market_cap, operating_income, interest_expense):
    if market_cap > 5 * 1e9:
        rating_mapping = [
            [-100000.0, 0.199999, "D", "20.00%"],
            [0.2, 0.649999, "C", "17.00%"],
            [0.65, 0.799999, "CC", "11.78%"],
            [0.8, 1.249999, "CCC", "8.51%"],
            [1.25, 1.499999, "B-", "5.24%"],
            [1.5, 1.749999, "B", "3.61%"],
            [1.75, 1.999999, "B+", "3.14%"],
            [2.0, 2.2499999, "BB", "2.21%"],
            [2.25, 2.49999, "BB+", "1.74%"],
            [2.5, 2.999999, "BBB", "1.47%"],
            [3.0, 4.249999, "A-", "1.21%"],
            [4.25, 5.499999, "A", "1.07%"],
            [5.5, 6.499999, "A+", "0.92%"],
            [6.5, 8.499999, "AA", "0.70%"],
            [8.5, 100000.0, "AAA", "0.59%"],
        ]
    else:
        rating_mapping = [
            [0.5, 0.799999, "C", "17.00%"],
            [0.8, 1.249999, "CC", "11.78%"],
            [1.25, 1.499999, "CCC", "8.51%"],
            [1.5, 1.999999, "B-", "5.24%"],
            [2.0, 2.499999, "B", "3.61%"],
            [2.5, 2.999999, "B+", "3.14%"],
            [3.0, 3.499999, "BB", "2.21%"],
            [3.5, 3.9999999, "BB+", "1.74%"],
            [4.0, 4.499999, "BBB", "1.47%"],
            [4.5, 5.999999, "A-", "1.21%"],
            [6.0, 7.499999, "A", "1.07%"],
            [7.5, 9.499999, "A+", "0.92%"],
            [9.5, 12.499999, "AA", "0.70%"],
            [12.5, 100000.0, "AAA", "0.59%"],
        ]

    if interest_expense <= 0:
        interest_coverage_rato = 100000
    elif operating_income <= 0:
        interest_coverage_rato = -100000
    else:
        interest_coverage_rato = operating_income / interest_expense

    rating, spread = None, None
    for low, high, r, s in rating_mapping:
        if low <= interest_coverage_rato <= high:
            rating, spread = r, s
            break
    if operating_income < 0:
        rating = "BB"
        spread = rating_mapping[7][3]
    default_prob = {
        "AAA": 0.70,
        "AA": 0.72,
        "A+": 0.72,
        "A": 1.24,
        "A-": 1.24,
        "BBB": 3.32,
        "BB+": 3.32,
        "BB": 11.78,
        "B+": 11.79,
        "B": 23.74,
        "B-": 23.75,
        "CCC": 50.38,
        "CC": 50.38,
        "C": 50.38,
        "D": 50.38,
    }[
        rating
    ] / 100  # in percentages
    spread = float(s.replace("%", "")) / 100
    return rating, spread, default_prob


def get_country_erp():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx"
    country_premium = pd.read_excel(url, sheet_name="ERPs by country", skiprows=7)
    countries = country_premium.iloc[:156][["Country", "Country Risk Premium"]].set_index("Country").to_dict()["Country Risk Premium"]
    frontier_countries = country_premium.iloc[158:179][["Country", "Moody's rating"]].set_index("Country").to_dict()["Moody's rating"]  # Table is concat at the bottom
    regions = pd.read_excel(url, sheet_name="Regional Weighted Averages")
    regions = regions.iloc[169:179][["Country", "Moody's rating"]].set_index("Country").to_dict()["Moody's rating"]
    return {**countries, **frontier_countries, **regions}


def get_industry_avgs():
    url = "https://pages.stern.nyu.edu/~adamodar/pc/fcffsimpleginzu.xlsx"
    df = pd.read_excel(url, sheet_name="Industry Averages(US)")
    return df.set_index("Industry Name").to_dict()


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
        print(f"[INFO] Could not find {ticker} on marketscreener")
    else:
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
        # print(f"[INFO] Could not find sales per region for {ticker}")
        return {"Global": 1}
    countries = df[df.columns[0]].values
    countries = [re.search(r"^([^\d]+)", item).group(0).strip() for item in countries]
    df["country"] = countries
    df.set_index("country", inplace=True)
    numeric_col_names = [x for x in df.columns if x.isdigit()]
    latest_year = max([int(x) for x in numeric_col_names])
    df = df[numeric_col_names]
    return df[str(latest_year)].to_dict()


def get_revenue_forecasts(url):
    default_forecasts = {
        "revenue_growth_rate_next_year": 0,
        "compounded_annual_revenue_growth_rate": 0,
        "operating_margin_next_year": 0,
        "consensus_revenues": {},
        "consensus_ebit": {},
        "currency": "",
        "unit": "",
    }
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
                return default_forecasts

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

    return default_forecasts


def get_statement_metric_series(statement: pd.DataFrame, metric_names: list[str]) -> pd.Series:
    for metric_name in metric_names:
        if metric_name in statement.index:
            return pd.to_numeric(statement.loc[metric_name], errors="coerce").fillna(0)
    return pd.Series(dtype=float)


def parse_timestamp(value):
    ts = pd.Timestamp(value, unit="s") if isinstance(value, (int, float)) else pd.Timestamp(value)
    return ts.tz_localize(None) if ts.tzinfo else ts


def get_fiscal_quarter_number(quarter_end: pd.Timestamp, fiscal_year_end: pd.Timestamp) -> int:
    month_delta = (quarter_end.month - fiscal_year_end.month - 1) % 12
    return month_delta // 3 + 1


def build_fiscal_bridge_context(info: dict, quarterly_income_statement: pd.DataFrame):
    if quarterly_income_statement.empty:
        return None

    last_fiscal_year_end = parse_timestamp(info.get("lastFiscalYearEnd"))
    if last_fiscal_year_end is None:
        return None

    revenue_series = get_statement_metric_series(
        quarterly_income_statement,
        ["Total Revenue", "Operating Revenue", "Revenue"],
    )
    if revenue_series.empty:
        return None

    operating_income_series = get_statement_metric_series(
        quarterly_income_statement,
        ["EBIT", "Operating Income"],
    )

    quarter_rows = [
        {
            "quarter_end": parse_timestamp(column),
            "revenue": float(revenue_series.get(column, 0)),
            "operating_income": float(operating_income_series.get(column, 0)),
        }
        for column in quarterly_income_statement.columns
    ]
    if not quarter_rows:
        return None

    quarters = pd.DataFrame(quarter_rows).sort_values("quarter_end", ascending=False).reset_index(drop=True)
    current_fiscal_year_end = last_fiscal_year_end + pd.DateOffset(years=1)
    current_fiscal_year = current_fiscal_year_end.year
    next_fiscal_year = current_fiscal_year + 1

    ytd_quarters = quarters[quarters["quarter_end"] > last_fiscal_year_end]
    quarters_reported = ytd_quarters.shape[0]
    if quarters_reported <= 0 or quarters_reported > 4:
        return None

    recent_four_quarters = quarters.head(4).copy()
    recent_four_quarters["fiscal_quarter"] = recent_four_quarters["quarter_end"].apply(
        lambda quarter_end: get_fiscal_quarter_number(quarter_end, last_fiscal_year_end)
    )
    recent_total_revenue = recent_four_quarters["revenue"].sum()
    if recent_total_revenue > 0 and recent_four_quarters["fiscal_quarter"].nunique() == 4:
        quarter_weights = {
            int(fq): v / recent_total_revenue
            for fq, v in recent_four_quarters.groupby("fiscal_quarter")["revenue"].sum().items()
        }
        next_fiscal_year_weight = sum(quarter_weights.get(q, 0) for q in range(1, quarters_reported + 1))
    else:
        next_fiscal_year_weight = quarters_reported / 4

    return {
        "current_fiscal_year": str(current_fiscal_year),
        "next_fiscal_year": str(next_fiscal_year),
        "quarters_reported": quarters_reported,
        "actual_ytd_revenue": float(ytd_quarters["revenue"].sum()),
        "actual_ytd_operating_income": float(ytd_quarters["operating_income"].sum()),
        "next_fiscal_year_weight": next_fiscal_year_weight,
    }


def bridge_fiscal_year_values(current_fiscal_value, next_fiscal_value, actual_ytd_value, next_fiscal_year_weight, clamp_remaining=False):
    if current_fiscal_value is None or next_fiscal_value is None:
        return None

    remaining_current_fiscal_value = current_fiscal_value - actual_ytd_value
    if clamp_remaining:
        remaining_current_fiscal_value = max(remaining_current_fiscal_value, 0)

    return remaining_current_fiscal_value + next_fiscal_year_weight * next_fiscal_value


def build_rolling_ntm_revenue_path(consensus_revenues: dict, bridge_context: dict):
    current_fiscal_year = int(bridge_context["current_fiscal_year"])
    next_fiscal_year_weight = bridge_context["next_fiscal_year_weight"]
    current_year_revenue = consensus_revenues.get(str(current_fiscal_year))
    next_year_revenue = consensus_revenues.get(str(current_fiscal_year + 1))
    if current_year_revenue is None or next_year_revenue is None:
        return []

    rolling_revenues = [
        bridge_fiscal_year_values(
            current_year_revenue,
            next_year_revenue,
            bridge_context["actual_ytd_revenue"],
            next_fiscal_year_weight,
            clamp_remaining=True,
        )
    ]

    for fiscal_year in range(current_fiscal_year + 1, current_fiscal_year + 3):
        current_value = consensus_revenues.get(str(fiscal_year))
        next_value = consensus_revenues.get(str(fiscal_year + 1))
        if current_value is None or next_value is None:
            break
        rolling_revenues.append((1 - next_fiscal_year_weight) * current_value + next_fiscal_year_weight * next_value)

    return [v for v in rolling_revenues if v is not None and np.isfinite(v)]


def get_similar_stocks(ticker: str):
    url = f"https://www.tipranks.com/stocks/{ticker.lower()}/similar-stocks"
    try:
        response = requests.get(url, headers=headers, proxies=get_proxy(), timeout=REQUEST_TIMEOUT_SECONDS)
    except:
        try:
            response = requests.get(url, headers=headers, proxies=get_proxy(), timeout=REQUEST_TIMEOUT_SECONDS)
        except:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)

    soup = BeautifulSoup(response.text, "html.parser")
    return [x.text for x in soup.find_all("a", {"data-link": "stock"})]


def r_and_d_handler(ticker, industry):
    url = f"https://ycharts.com/companies/{ticker.upper()}/r_and_d_expense_ttm"
    response = requests.get(
        url,
        headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    htmls = soup.find_all("table")
    try:
        df = pd.concat([pd.read_html(str(htmls))[0], pd.read_html(str(htmls))[1]]).iloc[::4]
        df["Value"] = df["Value"].apply(lambda x: {"B": 10**9, "M": 10**6, "K": 10**3}.get(x[-1], 1) * float(x[:-1]))
        expenses = df["Value"].tolist()
    except:
        expenses = [0]
    num_years = {
        "Advertising": 2,
        "Aerospace/Defense": 10,
        "Air Transport": 10,
        "Aluminum": 5,
        "Apparel": 3,
        "Auto & Truck": 10,
        "Auto Parts (OEM)": 5,
        "Auto Parts (Replacement)": 5,
        "Bank": 2,
        "Bank (Canadian)": 2,
        "Bank (Foreign)": 2,
        "Bank (Midwest)": 2,
        "Beverage (Alcoholic)": 3,
        "Beverage (Soft Drink)": 3,
        "Building Materials": 5,
        "Cable TV": 10,
        "Canadian Energy": 10,
        "Cement & Aggregates": 10,
        "Chemical (Basic)": 10,
        "Chemical (Diversified)": 10,
        "Chemical (Specialty)": 10,
        "Coal/Alternate Energy": 5,
        "Computer & Peripherals": 5,
        "Computer Software & Svcs": 3,
        "Copper": 5,
        "Diversified Co.": 5,
        "Drug": 10,
        "Drugstore": 3,
        "Educational Services": 3,
        "Electric Util. (Central)": 10,
        "Electric Utility (East)": 10,
        "Electric Utility (West)": 10,
        "Electrical Equipment": 10,
        "Electronics": 5,
        "Entertainment": 3,
        "Environmental": 5,
        "Financial Services": 2,
        "Food Processing": 3,
        "Food Wholesalers": 3,
        "Foreign Electron/Entertn": 5,
        "Foreign Telecom.": 10,
        "Furn./Home Furnishings": 3,
        "Gold/Silver Mining": 5,
        "Grocery": 2,
        "Healthcare Info Systems": 3,
        "Home Appliance": 5,
        "Homebuilding": 5,
        "Hotel/Gaming": 3,
        "Household Products": 3,
        "Industrial Services": 3,
        "Insurance (Diversified)": 3,
        "Insurance (Life)": 3,
        "Insurance (Prop/Casualty)": 3,
        "Internet": 3,
        "Investment Co. (Domestic)": 3,
        "Investment Co. (Foreign)": 3,
        "Investment Co. (Income)": 3,
        "Machinery": 10,
        "Manuf. Housing/Rec Veh": 5,
        "Maritime": 10,
        "Medical Services": 3,
        "Medical Supplies": 5,
        "Metal Fabricating": 10,
        "Metals & Mining (Div.)": 5,
        "Natural Gas (Distrib.)": 10,
        "Natural Gas (Diversified)": 10,
        "Newspaper": 3,
        "Office Equip & Supplies": 5,
        "Oilfield Services/Equip.": 5,
        "Packaging & Container": 5,
        "Paper & Forest Products": 10,
        "Petroleum (Integrated)": 5,
        "Petroleum (Producing)": 5,
        "Precision Instrument": 5,
        "Publishing": 3,
        "R.E.I.T.": 3,
        "Railroad": 5,
        "Recreation": 5,
        "Restaurant": 2,
        "Retail (Special Lines)": 2,
        "Retail Building Supply": 2,
        "Retail Store": 2,
        "Securities Brokerage": 2,
        "Semiconductor": 5,
        "Semiconductor Cap Equip": 5,
        "Shoe": 3,
        "Steel (General)": 5,
        "Steel (Integrated)": 5,
        "Telecom. Equipment": 10,
        "Telecom. Services": 5,
        "Textile": 5,
        "Thrift": 2,
        "Tire & Rubber": 5,
        "Tobacco": 5,
        "Toiletries/Cosmetics": 3,
        "Trucking/Transp. Leasing": 5,
        "Utility (Foreign)": 10,
        "Water Utility": 10,
    }.get(
        industry, 3
    )  # Default to 3 years
    num_years = min(len(expenses), num_years)
    expenses = np.array(expenses)[: num_years + 1]
    return expenses


def get_dcf_inputs(ticker: str, country_erps: dict, region_mapper: StringMapper, avg_metrics: dict, industry_mapper: StringMapper, mature_erp: float, risk_free_rate: float, fx_rates: dict):
    # Defaults
    average_maturity = 5
    marginal_tax_rate = 0.21
    value_of_options = 0

    ticker = yf.Ticker(ticker)
    quarterly_income_statement = normalize_quarterly_statement(ticker.quarterly_income_stmt)
    ttm_income_statement = quarterly_income_statement[quarterly_income_statement.columns[:4]].T.fillna(0)
    last_balance_sheet = ticker.quarterly_balance_sheet
    last_balance_sheet = last_balance_sheet[last_balance_sheet.columns[:4]].T.ffill().bfill()
    info = ticker.get_info()
    yahoo_profile = build_yahoo_profile(info.get("symbol", ticker.ticker), info)
    name = info.get("longName")
    curr_currency = info.get("financialCurrency")
    fx_rate = 1
    if curr_currency:
        resolved_fx_rate = fx_rates.get(curr_currency)
        if resolved_fx_rate:
            fx_rate = resolved_fx_rate
            last_balance_sheet = last_balance_sheet.apply(lambda x: x * fx_rate)
            ttm_income_statement["Operating Revenue"] = ttm_income_statement.get("Operating Revenue", 0) * fx_rate
            ttm_income_statement["Interest Expense"] = ttm_income_statement.get("Interest Expense", 0) * fx_rate
            ttm_income_statement["Pretax Income"] = ttm_income_statement.get("Pretax Income", 0) * fx_rate
            ttm_income_statement["Net Income"] = ttm_income_statement.get("Net Income", 0) * fx_rate
            ttm_income_statement["Operating Income"] = ttm_income_statement.get("Operating Income", 0) * fx_rate

    ttm_columns = list(quarterly_income_statement.columns[:4])
    revenue_series = get_statement_metric_series(
        quarterly_income_statement,
        ["Total Revenue", "Operating Revenue", "Revenue"],
    ).reindex(ttm_columns, fill_value=0) * fx_rate
    operating_income_series = get_statement_metric_series(
        quarterly_income_statement,
        ["EBIT", "Operating Income"],
    ).reindex(ttm_columns, fill_value=0) * fx_rate
    interest_expense_series = get_statement_metric_series(
        quarterly_income_statement,
        ["Interest Expense"],
    ).reindex(ttm_columns, fill_value=0) * fx_rate
    pretax_income_series = get_statement_metric_series(
        quarterly_income_statement,
        ["Pretax Income"],
    ).reindex(ttm_columns, fill_value=0) * fx_rate
    tax_rate_series = get_statement_metric_series(
        quarterly_income_statement,
        ["Tax Rate For Calcs"],
    ).reindex(ttm_columns, fill_value=0)

    revenues = revenue_series.sum()
    operating_income_ttm = operating_income_series.sum()
    interest_expense = interest_expense_series.sum()
    book_value_of_equity = last_balance_sheet.get("Stockholders Equity", pd.Series([0])).iloc[0]
    book_value_of_debt = last_balance_sheet.get("Total Debt", pd.Series([0])).iloc[0]
    cash_and_marketable_securities = last_balance_sheet.get("Cash Cash Equivalents And Short Term Investments", pd.Series([0])).iloc[0]
    cross_holdings_and_other_non_operating_assets = last_balance_sheet.get("Investments And Advances", pd.Series([0])).iloc[0]
    minority_interest = last_balance_sheet.get("Minority Interest", pd.Series([0])).iloc[0]  # by right. should convert to market value
    number_of_shares_outstanding = info.get("sharesOutstanding", 0)
    curr_price = info.get("previousClose", 0)
    pretax_income_total = pretax_income_series.sum()
    effective_tax_rate = (tax_rate_series * pretax_income_series).sum() / pretax_income_total if pretax_income_total else 0

    regions = region_mapper.get_closest(info["country"])

    industry = info["industry"]
    sector = info["sector"]
    avg_betas = avg_metrics["Unlevered Beta"]
    unlevered_beta, industry = get_industry_beta(industry, sector, industry_mapper, avg_betas)
    marketscreener_url = get_marketscreener_url(info["symbol"], info["shortName"])

    regional_revenues = get_revenue_by_region(info["symbol"], marketscreener_url)
    equity_risk_premium, mapped_regional_revenues = get_regional_crps(regional_revenues, region_mapper, country_erps)
    equity_risk_premium = equity_risk_premium + mature_erp
    _, company_spread, prob_of_failure = synthetic_rating(info["marketCap"], operating_income_ttm, interest_expense)
    pre_tax_cost_of_debt = risk_free_rate + company_spread + country_erps[regions[0]]

    target_pre_tax_operating_margin = avg_metrics["Pre-tax Operating Margin (Unadjusted)"][industry]

    operating_margin_this_year = info.get("operatingMargins", operating_income_ttm / revenues if revenues else 0)

    forecast_defaults = get_revenue_forecasts(marketscreener_url)
    consensus_revenues_usd = {
        year: value * fx_rate
        for year, value in forecast_defaults.get("consensus_revenues", {}).items()
    }
    consensus_ebit_usd = {
        year: value * fx_rate
        for year, value in forecast_defaults.get("consensus_ebit", {}).items()
    }
    fiscal_bridge_context = build_fiscal_bridge_context(info, quarterly_income_statement)
    current_fiscal_year = None
    next_fiscal_year = None
    bridged_ntm_revenue = None
    bridged_ntm_operating_income = None
    rolling_ntm_revenues = []
    revenue_growth_rate_next_year = forecast_defaults.get("revenue_growth_rate_next_year", 0)
    if fiscal_bridge_context:
        current_fiscal_year = fiscal_bridge_context["current_fiscal_year"]
        next_fiscal_year = fiscal_bridge_context["next_fiscal_year"]
        current_fiscal_year_consensus = consensus_revenues_usd.get(current_fiscal_year)
        next_fiscal_year_consensus = consensus_revenues_usd.get(next_fiscal_year)
        bridged_ntm_revenue = bridge_fiscal_year_values(
            current_fiscal_year_consensus,
            next_fiscal_year_consensus,
            fiscal_bridge_context["actual_ytd_revenue"],
            fiscal_bridge_context["next_fiscal_year_weight"],
            clamp_remaining=True,
        )
        if bridged_ntm_revenue and revenues:
            revenue_growth_rate_next_year = bridged_ntm_revenue / revenues - 1
        rolling_ntm_revenues = build_rolling_ntm_revenue_path(consensus_revenues_usd, fiscal_bridge_context)
    else:
        curr_year = datetime.datetime.now().year - 1
        next_fiscal_year = str(curr_year + 2)
        next_fiscal_year_consensus = consensus_revenues_usd.get(next_fiscal_year)
        if next_fiscal_year_consensus and revenues:
            revenue_growth_rate_next_year = next_fiscal_year_consensus / revenues - 1

    post_bridge_years = sorted(
        [year for year in consensus_revenues_usd.keys() if int(year) >= int(next_fiscal_year)],
        key=int,
    )
    post_bridge_growth_rates = []
    for previous_year, later_year in zip(post_bridge_years, post_bridge_years[1:]):
        previous_value = consensus_revenues_usd.get(previous_year, 0)
        later_value = consensus_revenues_usd.get(later_year, 0)
        if previous_value:
            post_bridge_growth_rates.append(later_value / previous_value - 1)

    rolling_ntm_growth_rates = []
    for current_value, next_value in zip(rolling_ntm_revenues, rolling_ntm_revenues[1:]):
        if current_value:
            rolling_ntm_growth_rates.append(next_value / current_value - 1)
    compounded_annual_revenue_growth_rate = (
        float(np.mean(rolling_ntm_growth_rates))
        if rolling_ntm_growth_rates
        else float(np.mean(post_bridge_growth_rates))
        if post_bridge_growth_rates
        else forecast_defaults.get("compounded_annual_revenue_growth_rate", 0)
    )
    operating_margin_next_year = forecast_defaults.get("operating_margin_next_year", 0)
    if fiscal_bridge_context:
        current_fiscal_year_consensus_ebit = consensus_ebit_usd.get(current_fiscal_year)
        next_fiscal_year_consensus_ebit = consensus_ebit_usd.get(next_fiscal_year)
        bridged_ntm_operating_income = bridge_fiscal_year_values(
            current_fiscal_year_consensus_ebit,
            next_fiscal_year_consensus_ebit,
            fiscal_bridge_context["actual_ytd_operating_income"],
            fiscal_bridge_context["next_fiscal_year_weight"],
        )
        if bridged_ntm_operating_income is not None and bridged_ntm_revenue not in (None, 0):
            operating_margin_next_year = bridged_ntm_operating_income / bridged_ntm_revenue
    operating_margin_next_year = max(operating_margin_next_year, operating_margin_this_year)
    target_pre_tax_operating_margin = max(target_pre_tax_operating_margin, operating_margin_next_year)
    year_of_convergence_for_margin = 5
    years_of_high_growth = 5
    curr_sales_to_capital_ratio = revenues / (book_value_of_equity + book_value_of_debt - cash_and_marketable_securities - cross_holdings_and_other_non_operating_assets)
    sales_to_capital_ratio_early = curr_sales_to_capital_ratio
    sales_to_capital_ratio_steady = avg_metrics["Sales/Capital"][industry]
    r_and_d_expenses = r_and_d_handler(info["symbol"], industry)
    return {
        "dcf_inputs": {
            "name": name,
            "revenues": revenues,
            "operating_income": operating_income_ttm,
            "interest_expense": interest_expense,
            "book_value_of_equity": book_value_of_equity,
            "book_value_of_debt": book_value_of_debt,
            "cash_and_marketable_securities": cash_and_marketable_securities,
            "cross_holdings_and_other_non_operating_assets": cross_holdings_and_other_non_operating_assets,
            "minority_interest": minority_interest,
            "number_of_shares_outstanding": number_of_shares_outstanding,
            "curr_price": curr_price,
            "effective_tax_rate": effective_tax_rate,
            "marginal_tax_rate": marginal_tax_rate,
            "unlevered_beta": unlevered_beta,
            "risk_free_rate": risk_free_rate,
            "equity_risk_premium": equity_risk_premium,
            "mature_erp": mature_erp,
            "pre_tax_cost_of_debt": pre_tax_cost_of_debt,
            "average_maturity": average_maturity,
            "prob_of_failure": prob_of_failure,
            "value_of_options": value_of_options,
            "revenue_growth_rate_next_year": revenue_growth_rate_next_year,
            "operating_margin_next_year": operating_margin_next_year,
            "compounded_annual_revenue_growth_rate": compounded_annual_revenue_growth_rate,
            "target_pre_tax_operating_margin": target_pre_tax_operating_margin,
            "year_of_convergence_for_margin": year_of_convergence_for_margin,
            "years_of_high_growth": years_of_high_growth,
            "sales_to_capital_ratio_early": sales_to_capital_ratio_early,
            "sales_to_capital_ratio_steady": sales_to_capital_ratio_steady,
            "extras": {
                "regional_revenues": regional_revenues,
                "industry": industry,
                "historical_revenue_growth": info.get("revenueGrowth", 0),
                "mapped_regional_revenues": mapped_regional_revenues,
                "similar_stocks": get_similar_stocks(info["symbol"]),
                "research_and_development": r_and_d_expenses,
                "last_updated_financials": ttm_income_statement.index[0].strftime("%Y-%m-%d"),
                "forecast_context": {
                    "consensus_revenues": consensus_revenues_usd,
                    "consensus_ebit": consensus_ebit_usd,
                    "ms_growth_next_year": forecast_defaults.get("revenue_growth_rate_next_year", 0),
                    "ms_margin_next_year": forecast_defaults.get("operating_margin_next_year", 0),
                    "current_fiscal_year": current_fiscal_year,
                    "next_fiscal_year": next_fiscal_year,
                    "quarters_reported": fiscal_bridge_context["quarters_reported"] if fiscal_bridge_context else None,
                    "actual_ytd_revenue": fiscal_bridge_context["actual_ytd_revenue"] if fiscal_bridge_context else None,
                    "actual_ytd_operating_income": fiscal_bridge_context["actual_ytd_operating_income"] if fiscal_bridge_context else None,
                    "next_fiscal_year_weight": fiscal_bridge_context["next_fiscal_year_weight"] if fiscal_bridge_context else None,
                    "bridged_ntm_revenue": bridged_ntm_revenue,
                    "bridged_ntm_operating_income": bridged_ntm_operating_income,
                    "rolling_ntm_revenues": rolling_ntm_revenues,
                },
            },
        },
        "yahoo_profile": yahoo_profile,
    }


def get_marketscreener_links(tickers):
    links = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_marketscreener_url, ticker): ticker for ticker in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                link = future.result()
                if not link:
                    continue
                if not link.endswith("/"):
                    link += "/"
                links[ticker] = link + "finances/"
            except Exception:
                continue

    return links


def parse_marketscreener(marketscreener_urls):
    if not marketscreener_urls:
        return pd.DataFrame()

    htmls = get_htmls(list(marketscreener_urls.values()))
    htmls = dict(zip(marketscreener_urls.keys(), htmls))
    dfs = []

    for ticker, html in htmls.items():
        if not html:
            continue
        try:
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
        except Exception as e:
            print("[ERROR] Failed to parse Marketscreener", ticker, e)

    if not dfs:
        return pd.DataFrame()

    marketscreener = pd.concat(dfs, axis=0, join="outer", ignore_index=True)
    return marketscreener.reset_index(drop=True).fillna(0).set_index("Ticker")


def build_yahoo_profile(ticker, ticker_info):
    return {
        "Ticker": ticker,
        "Name": ticker_info.get("longName"),
        "Market Cap": ticker_info.get("marketCap"),
        "Sector": ticker_info.get("sector"),
        "Summary": ticker_info.get("longBusinessSummary"),
        "Industry": ticker_info.get("industry"),
        "Shares Outstanding": ticker_info.get("sharesOutstanding"),
        "Institution Ownership": ticker_info.get("heldPercentInstitutions"),
        "Price": ticker_info.get("currentPrice"),
        "52-Week High": ticker_info.get("fiftyTwoWeekHigh"),
        "52-Week Low": ticker_info.get("fiftyTwoWeekLow"),
        "P/E": ticker_info.get("trailingPE"),
        "Forward PE": ticker_info.get("forwardPE"),
        "Price to Sales": ticker_info.get("priceToSalesTrailing12Months"),
        "Enterprise Value": ticker_info.get("enterpriseValue"),
        "Beta": ticker_info.get("beta"),
    }


def normalize_quarterly_statement(statement: pd.DataFrame) -> pd.DataFrame:
    if statement is None or statement.empty:
        return pd.DataFrame()

    statement = statement.copy()
    statement = statement.loc[~statement.index.duplicated(keep="first")]
    ordered_columns = sorted(statement.columns, key=lambda column: pd.Timestamp(column), reverse=True)
    return statement.loc[:, ordered_columns].fillna(0)


def sum_statement_metric(statement: pd.DataFrame, metric_names: list[str], start=0, count=4):
    columns = list(statement.columns[start : start + count])

    for metric_name in metric_names:
        if metric_name in statement.index:
            values = pd.to_numeric(statement.loc[metric_name, columns], errors="coerce").fillna(0)
            return float(values.sum())

    return None


def compute_ebitda(statement: pd.DataFrame, start=0, count=4):
    ebitda = sum_statement_metric(statement, ["EBITDA"], start=start, count=count)

    ebit = sum_statement_metric(statement, ["EBIT", "Operating Income"], start=start, count=count)
    depreciation = sum_statement_metric(
        statement,
        [
            "Depreciation And Amortization",
            "Depreciation Amortization Depletion Income Statement",
            "Reconciled Depreciation",
        ],
        start=start,
        count=count,
    )
    if ebit is None or depreciation is None:
        return None
    return ebit + depreciation


def get_ttm_financials(ticker):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            yf_ticker = yf.Ticker(ticker)
            quarterly_income_stmt = normalize_quarterly_statement(yf_ticker.quarterly_income_stmt)
            if quarterly_income_stmt.empty:
                return None

            most_recent_quarter = quarterly_income_stmt.columns[0]
            result = {
                "Ticker": ticker,
                "Revenue TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["Total Revenue", "Operating Revenue", "Revenue"],
                ),
                "Revenue Prev TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["Total Revenue", "Operating Revenue", "Revenue"],
                    start=4,
                    count=4,
                ),
                "Net Income TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    [
                        "Net Income Common Stockholders",
                        "Net Income Including Noncontrolling Interests",
                        "Net Income",
                    ],
                ),
                "Net Income Prev TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    [
                        "Net Income Common Stockholders",
                        "Net Income Including Noncontrolling Interests",
                        "Net Income",
                    ],
                    start=4,
                    count=4,
                ),
                "EBITDA TTM": compute_ebitda(quarterly_income_stmt),
                "EBITDA Prev TTM": compute_ebitda(quarterly_income_stmt, start=4, count=4),
                "EBIT TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["EBIT", "Operating Income"],
                ),
                "EBIT Prev TTM": sum_statement_metric(
                    quarterly_income_stmt,
                    ["EBIT", "Operating Income"],
                    start=4,
                    count=4,
                ),
                "TTM Period End": pd.Timestamp(most_recent_quarter).strftime("%Y-%m-%d"),
            }
            return result
        except YFRateLimitError:
            if attempt == YAHOO_INFO_RETRIES - 1:
                print(f"[ERROR] Yahoo rate limited for {ticker} TTM after {YAHOO_INFO_RETRIES} attempts")
                return None

            sleep_seconds = YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1)
            print(f"[WARN] Yahoo rate limited for {ticker} TTM; retrying in {sleep_seconds:.1f}s")
            time.sleep(sleep_seconds)
        except Exception as e:
            print(f"[ERROR] Failed to fetch TTM financials for {ticker}: {e}")
            return None


def compute_ttm_financials(tickers):
    ttm_financials_by_ticker = {}
    for i in range(0, len(tickers), YAHOO_INFO_MAX_WORKERS):
        batch = tickers[i : i + YAHOO_INFO_MAX_WORKERS]
        with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
            results = list(executor.map(get_ttm_financials, batch))
        for result in results:
            if result:
                ttm_financials_by_ticker[result["Ticker"]] = result

        if i + YAHOO_INFO_MAX_WORKERS < len(tickers):
            time.sleep(1)

    ordered_financials = [ttm_financials_by_ticker[ticker] for ticker in tickers if ticker in ttm_financials_by_ticker]
    if not ordered_financials:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_financials).set_index("Ticker")


def get_info(ticker):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            ticker_info = yf.Ticker(ticker).get_info()
            return build_yahoo_profile(ticker, ticker_info)
        except YFRateLimitError:
            if attempt == YAHOO_INFO_RETRIES - 1:
                print(f"[ERROR] Yahoo rate limited for {ticker} after {YAHOO_INFO_RETRIES} attempts")
                return None

            sleep_seconds = YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1)
            print(f"[WARN] Yahoo rate limited for {ticker}; retrying in {sleep_seconds:.1f}s")
            time.sleep(sleep_seconds)
        except Exception as e:
            print(f"[ERROR] Failed to fetch Yahoo profile for {ticker}: {e}")
            return None


def get_and_parse_yahoo(tickers, cached_profiles=None):
    cached_profiles = cached_profiles or {}
    profiles_by_ticker = {}

    for ticker in tickers:
        cached_profile = cached_profiles.get(ticker)
        if cached_profile:
            profiles_by_ticker[ticker] = cached_profile

    missing_tickers = [ticker for ticker in tickers if ticker not in profiles_by_ticker]
    if missing_tickers:
        for i in range(0, len(missing_tickers), YAHOO_INFO_MAX_WORKERS):
            batch = missing_tickers[i : i + YAHOO_INFO_MAX_WORKERS]
            with concurrent.futures.ThreadPoolExecutor(max_workers=YAHOO_INFO_MAX_WORKERS) as executor:
                results = list(executor.map(get_info, batch))
            for result in results:
                if result:
                    profiles_by_ticker[result["Ticker"]] = result

            if i + YAHOO_INFO_MAX_WORKERS < len(missing_tickers):
                time.sleep(1)

    ordered_profiles = [profiles_by_ticker[ticker] for ticker in tickers if ticker in profiles_by_ticker]
    if not ordered_profiles:
        return pd.DataFrame(columns=["Ticker"]).set_index("Ticker")

    return pd.DataFrame(ordered_profiles).set_index("Ticker")


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


def run_dcf_scrape(tickers, client):
    country_erps = get_country_erp()
    region_mapper = StringMapper(list(country_erps.keys()))
    avg_metrics = get_industry_avgs()
    avg_betas = avg_metrics["Unlevered Beta"]
    industry_mapper = StringMapper(list(avg_betas.keys()))
    risk_free_rate = get_10year_tbill()
    mature_erp = get_mature_erp()
    fx_rates = get_exchange_rates()

    db_name = os.getenv("MONGODB_DB_NAME")
    dcf_db = client[db_name]["dcf_inputs"]
    num_errors = 0
    yahoo_profiles = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for i, ticker in enumerate(tickers):
            if i > 0 and i % MAX_WORKERS == 0:
                time.sleep(1)
            future = executor.submit(process_ticker, ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, dcf_db, fx_rates)
            futures.append(future)

        for future in concurrent.futures.as_completed(futures):
            success, yahoo_profile = future.result()
            if not success:
                num_errors += 1
            elif yahoo_profile:
                yahoo_profiles[yahoo_profile["Ticker"]] = yahoo_profile

    print(f"Number of DCF errors: {num_errors} out of {len(tickers)} tickers")

    macro_db = client[db_name]["macro"]
    macro_db.update_one(
        filter={},
        update={
            "$set": {
                "Macro": {
                    "Country ERPs": country_erps,
                    "Avg Metrics": avg_metrics,
                    "Risk Free Rate": risk_free_rate,
                    "Mature ERP": mature_erp,
                }
            }
        },
        upsert=True,
    )
    return yahoo_profiles


def run_comps_scrape(tickers, client, cached_yahoo_profiles=None):
    yahoo_df = get_and_parse_yahoo(tickers, cached_profiles=cached_yahoo_profiles)
    ttm_financials_df = compute_ttm_financials(tickers)
    finviz_df = parse_finviz(tickers)

    combined = pd.concat([yahoo_df, ttm_financials_df, finviz_df], axis=1, join="outer")
    combined = combined.fillna(0)
    if "TTM Period End" in combined.columns:
        combined["TTM Period End"] = combined["TTM Period End"].replace(0, None)
    combined.reset_index(inplace=True)
    combined = combined.rename(columns={"index": "Ticker"})
    combined.sort_values("Ticker", inplace=True)

    db = client[os.getenv("MONGODB_DB_NAME")]["financials"]
    data = combined.to_dict(orient="records")
    data = json.loads(json.dumps(data, cls=CustomEncoder))
    for record in data:
        db.update_one({"Ticker": record["Ticker"]}, {"$set": record}, upsert=True)


def main():
    tickers = get_all_tickers()
    print("Number of tickers:", len(tickers))
    client = get_mongo_client()
    yahoo_profiles = run_dcf_scrape(tickers, client)
    print("Running comps scrape")
    run_comps_scrape(tickers, client, cached_yahoo_profiles=yahoo_profiles)


def process_ticker(ticker, country_erps, region_mapper, avg_metrics, industry_mapper, mature_erp, risk_free_rate, db, fx_rates):
    try:
        dcf_result = run_with_timeout(
            get_dcf_inputs,
            TICKER_TIMEOUT_SECONDS,
            ticker,
            country_erps,
            region_mapper,
            avg_metrics,
            industry_mapper,
            mature_erp,
            risk_free_rate,
            fx_rates,
        )
        dcf_inputs = json.dumps(dcf_result["dcf_inputs"], cls=CustomEncoder)
        dcf_inputs = json.loads(dcf_inputs)
        db.update_one({"Ticker": ticker}, {"$set": dcf_inputs}, upsert=True)
        return True, dcf_result.get("yahoo_profile")
    except TimeoutError:
        print(f"Ticker {ticker} timed out after {TICKER_TIMEOUT_SECONDS} seconds")
        return False, None
    except Exception as e:
        print(f"Ticker {ticker} error: {e}")
        return False, None


if __name__ == "__main__":
    main()
