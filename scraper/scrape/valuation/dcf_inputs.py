import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from scrape.core.config import REQUEST_TIMEOUT_SECONDS, headers
from scrape.core.http_utils import get_proxy
from scrape.sources.marketscreener import get_marketscreener_url, get_revenue_by_region, get_revenue_forecasts
from scrape.sources.yahoo_profiles import build_yahoo_profile, normalize_quarterly_statement
from scrape.valuation.market_metrics import get_industry_beta, get_regional_crps, synthetic_rating
from scrape.valuation.statements import (
    bridge_fiscal_year_values,
    build_fiscal_bridge_context,
    build_rolling_ntm_revenue_path,
    get_statement_metric_series,
)
from scrape.valuation.string_mapper import StringMapper


def get_similar_stocks(ticker: str):
    url = f"https://www.tipranks.com/stocks/{ticker.lower()}/similar-stocks"
    response = requests.get(
        url,
        headers=headers,
        proxies=get_proxy(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

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
    df = pd.concat([pd.read_html(str(htmls))[0], pd.read_html(str(htmls))[1]]).iloc[::4]
    df["Value"] = df["Value"].apply(lambda x: {"B": 10**9, "M": 10**6, "K": 10**3}.get(x[-1], 1) * float(x[:-1]))
    expenses = df["Value"].tolist()
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


def _balance_sheet_scalar(df: pd.DataFrame, key: str) -> float:
    if key not in df.columns:
        raise KeyError(f"Balance sheet line item missing: {key}")
    val = df[key].iloc[0]
    if pd.isna(val):
        raise ValueError(f"Balance sheet line item {key!r} is NaN")
    return float(val)


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
        if curr_currency not in fx_rates:
            raise KeyError(f"No FX rate for reporting currency {curr_currency!r}")
        fx_rate = fx_rates[curr_currency]
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
    book_value_of_equity = _balance_sheet_scalar(last_balance_sheet, "Stockholders Equity")
    book_value_of_debt = _balance_sheet_scalar(last_balance_sheet, "Total Debt")
    cash_and_marketable_securities = _balance_sheet_scalar(
        last_balance_sheet, "Cash Cash Equivalents And Short Term Investments"
    )
    cross_holdings_and_other_non_operating_assets = _balance_sheet_scalar(
        last_balance_sheet, "Investments And Advances"
    )
    minority_interest = _balance_sheet_scalar(last_balance_sheet, "Minority Interest")  # by right. should convert to market value
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
