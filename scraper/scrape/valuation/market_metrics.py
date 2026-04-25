import pandas as pd
import requests

from scrape.core.config import CURRENCIES, REQUEST_TIMEOUT_SECONDS, headers
from scrape.core.yahoo_client import yahoo_ticker
from scrape.valuation.string_mapper import StringMapper


def get_exchange_rates():
    fx_rate = {}
    for currency in CURRENCIES:
        fx_rate[currency] = yahoo_ticker(currency + "USD=X").history().Close.iloc[-1].item()
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
    raw = res["FormattedQuoteResult"]["FormattedQuote"][0]["last"]
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
