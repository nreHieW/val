import concurrent.futures
import datetime
import logging
import random
import time

import numpy as np
import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from scrape.core.config import YAHOO_INFO_RETRIES, YAHOO_INFO_RETRY_SLEEP_SECONDS
from scrape.sources.marketscreener import get_marketscreener_url, get_revenue_by_region, get_revenue_forecasts
from scrape.sources.yahoo_overview import build_yahoo_overview
from scrape.sources.yahoo_profiles import build_yahoo_profile, normalize_quarterly_statement
from scrape.valuation.market_metrics import get_industry_beta, get_regional_crps, synthetic_rating
from scrape.valuation.statements import (
    bridge_fiscal_year_values,
    build_fiscal_bridge_context,
    build_rolling_ntm_revenue_path,
    get_statement_metric_series,
)
from scrape.valuation.string_mapper import StringMapper

logger = logging.getLogger(__name__)


def _is_transient_yahoo_error(exc):
    if isinstance(exc, (YFRateLimitError, TimeoutError, ConnectionError, IndexError)):
        return True
    message = str(exc).lower()
    return any(token in message for token in ("rate limit", "too many requests", "crumb", "cookie", "timeout"))


def _with_yahoo_retries(label, func):
    for attempt in range(YAHOO_INFO_RETRIES):
        try:
            return func()
        except Exception as exc:
            if attempt == YAHOO_INFO_RETRIES - 1 or not _is_transient_yahoo_error(exc):
                raise
            sleep_seconds = YAHOO_INFO_RETRY_SLEEP_SECONDS * (attempt + 1) + random.uniform(0, 0.75)
            logger.debug("%s Yahoo failure (%s); retrying in %.1fs", label, exc, sleep_seconds)
            time.sleep(sleep_seconds)


def _balance_sheet_scalar(df: pd.DataFrame, key: str, default: float = 0) -> float:
    """First value for a Yahoo line item. If the column exists but is all-NaN, iloc[0] is NaN — use default."""
    series = df.get(key, pd.Series([default]))
    val = series.iloc[0]
    return float(default) if pd.isna(val) else float(val)


def _usd_fx_rate(currency: str | None, fx_rates: dict) -> float:
    """Return the USD conversion rate for one unit of currency.

    Missing FX data should not kill the entire DCF run. When Yahoo and the
    supplied table both miss a rate, keep the scrape moving with a 1.0 fallback
    and emit a warning that includes the Yahoo pair we attempted.
    """
    if not currency:
        return 1.0

    currency = str(currency).strip().upper()
    if currency == "USD":
        return 1.0

    resolved = fx_rates.get(currency)
    if resolved:
        return float(resolved)

    # Yahoo sometimes reports London prices in pence (GBX/GBP=X). DCF
    # financial statements are usually already in GBP, but handle pence if seen.
    if currency in {"GBX", "GBP=X"}:
        resolved = fx_rates.get("GBP")
        if resolved:
            return float(resolved) / 100

    yahoo_pair = f"{currency}USD=X"
    try:
        history = yf.Ticker(yahoo_pair).history(period="5d")
        close = history.Close.dropna()
        if not close.empty:
            return float(close.iloc[-1].item())
    except Exception as exc:
        logger.warning("FX lookup failed for %s via %s: %s", currency, yahoo_pair, exc)
        return 1.0

    logger.warning("Missing USD FX rate for %s via %s; using 1.0 fallback", currency, yahoo_pair)
    return 1.0


def _income_statement_for_dcf(ticker: yf.Ticker) -> tuple[pd.DataFrame, bool]:
    """Prefer quarterly income statement; fall back to annual when Yahoo has no quarterlies."""
    quarterly = normalize_quarterly_statement(
        _with_yahoo_retries(ticker.ticker + " quarterly_income_stmt", lambda: ticker.quarterly_income_stmt)
    )
    if not quarterly.empty:
        return quarterly, False

    annual = normalize_quarterly_statement(
        _with_yahoo_retries(ticker.ticker + " income_stmt", lambda: ticker.income_stmt)
    )
    if not annual.empty:
        logger.warning("%s missing quarterly income statement; using latest annual periods for DCF inputs", ticker.ticker)
        return annual, True

    logger.warning("%s missing both quarterly and annual income statements; cannot build DCF inputs", ticker.ticker)
    return pd.DataFrame(), False


def r_and_d_handler(income_statement: pd.DataFrame, industry: str):
    r_and_d_series = get_statement_metric_series(
        income_statement,
        ["Research And Development", "Research Development"],
    )
    expenses = [float(value) for value in r_and_d_series.dropna().tolist() if value > 0]
    if not expenses:
        raise ValueError("No R&D expense history")
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
    quarterly_income_statement, using_annual_income_statement = _income_statement_for_dcf(ticker)
    if quarterly_income_statement.empty:
        raise ValueError(f"missing_income_statement:{ticker.ticker}")
    ttm_columns = list(quarterly_income_statement.columns[:1] if using_annual_income_statement else quarterly_income_statement.columns[:4])
    ttm_income_statement = quarterly_income_statement.loc[:, ttm_columns].T.fillna(0)
    last_balance_sheet = _with_yahoo_retries(ticker.ticker + " quarterly_balance_sheet", lambda: ticker.quarterly_balance_sheet)
    if last_balance_sheet.empty:
        last_balance_sheet = _with_yahoo_retries(ticker.ticker + " balance_sheet", lambda: ticker.balance_sheet)
        if not last_balance_sheet.empty:
            logger.warning("%s missing quarterly balance sheet; using latest annual balance sheet", ticker.ticker)
    if last_balance_sheet.empty:
        last_balance_sheet = pd.DataFrame([{}])
    else:
        last_balance_sheet = last_balance_sheet[last_balance_sheet.columns[:4]].T.ffill().bfill()
    info = _with_yahoo_retries(ticker.ticker + " info", lambda: ticker.get_info() or {})

    symbol = info.get("symbol") or ticker.ticker
    yahoo_profile = build_yahoo_profile(symbol, info)
    try:
        yahoo_overview = build_yahoo_overview(ticker, info)
    except Exception as e:
        logger.debug("%s overview skipped: %s", ticker.ticker, e)
        yahoo_overview = None
    name = info.get("longName") or info.get("shortName") or symbol
    curr_currency = info.get("financialCurrency")
    fx_rate = _usd_fx_rate(curr_currency, fx_rates)
    if fx_rate != 1:
        last_balance_sheet = last_balance_sheet.apply(lambda x: x * fx_rate)
        ttm_income_statement["Operating Revenue"] = ttm_income_statement.get("Operating Revenue", 0) * fx_rate
        ttm_income_statement["Interest Expense"] = ttm_income_statement.get("Interest Expense", 0) * fx_rate
        ttm_income_statement["Pretax Income"] = ttm_income_statement.get("Pretax Income", 0) * fx_rate
        ttm_income_statement["Net Income"] = ttm_income_statement.get("Net Income", 0) * fx_rate
        ttm_income_statement["Operating Income"] = ttm_income_statement.get("Operating Income", 0) * fx_rate

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

    country = info.get("country")
    regions = region_mapper.get_closest(country) if country else ["Global"]

    industry = info.get("industry") or info.get("sector") or "Grand Total"
    sector = info.get("sector") or industry
    avg_betas = avg_metrics["Unlevered Beta"]
    unlevered_beta, industry = get_industry_beta(industry, sector, industry_mapper, avg_betas)
    marketscreener_url = get_marketscreener_url(symbol, info.get("shortName") or info.get("longName") or "")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        regional_revenues_future = executor.submit(get_revenue_by_region, symbol, marketscreener_url)
        forecast_defaults_future = executor.submit(get_revenue_forecasts, marketscreener_url)

        try:
            regional_revenues = regional_revenues_future.result()
        except Exception as e:
            logger.debug("%s regional revenue unavailable; using country fallback: %s", symbol, e)
            regional_revenues = {country or "Global": revenues if revenues else 1}
        try:
            forecast_defaults = forecast_defaults_future.result()
        except Exception as e:
            logger.debug("%s revenue forecasts unavailable; using defaults: %s", symbol, e)
            forecast_defaults = {}

    equity_risk_premium, mapped_regional_revenues = get_regional_crps(regional_revenues, region_mapper, country_erps)
    equity_risk_premium = equity_risk_premium + mature_erp
    _, company_spread, prob_of_failure = synthetic_rating(info.get("marketCap", 0), operating_income_ttm, interest_expense)
    pre_tax_cost_of_debt = risk_free_rate + company_spread + country_erps.get(regions[0], country_erps.get("Global", 0))

    target_pre_tax_operating_margin = avg_metrics["Pre-tax Operating Margin (Unadjusted)"].get(industry, 0)

    operating_margin_this_year = info.get("operatingMargins", operating_income_ttm / revenues if revenues else 0)
    forecast_fx_rate = _usd_fx_rate(forecast_defaults.get("currency") or curr_currency, fx_rates)
    consensus_revenues_usd = {
        year: value * forecast_fx_rate
        for year, value in forecast_defaults.get("consensus_revenues", {}).items()
    }
    consensus_ebit_usd = {
        year: value * forecast_fx_rate
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
    invested_capital = book_value_of_equity + book_value_of_debt - cash_and_marketable_securities - cross_holdings_and_other_non_operating_assets
    curr_sales_to_capital_ratio = revenues / invested_capital if invested_capital else avg_metrics["Sales/Capital"].get(industry, 1)
    sales_to_capital_ratio_early = curr_sales_to_capital_ratio
    sales_to_capital_ratio_steady = avg_metrics["Sales/Capital"].get(industry, 1)
    try:
        annual_income_stmt = _with_yahoo_retries(ticker.ticker + " income_stmt", lambda: ticker.income_stmt)
        r_and_d_expenses = r_and_d_handler(annual_income_stmt, industry)
    except Exception as e:
        logger.debug("%s R&D expense unavailable; using empty history: %s", symbol, e)
        r_and_d_expenses = []
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
        "yahoo_overview": yahoo_overview,
    }
