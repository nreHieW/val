from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .modelling import dcf, calc_cost_of_capital
from pydantic import BaseModel
import yfinance as yf


class CostOfCapitalRequest(BaseModel):
    interest_expense: float
    pre_tax_cost_of_debt: float
    average_maturity: int
    bv_debt: float
    num_shares_outstanding: int
    curr_price: float
    unlevered_beta: float
    tax_rate: float
    risk_free_rate: float
    equity_risk_premium: float


class DCFRequest(BaseModel):
    revenues: float
    operating_income: float
    interest_expense: float
    book_value_of_equity: float
    book_value_of_debt: float
    cash_and_marketable_securities: float
    cross_holdings_and_other_non_operating_assets: float
    minority_interest: float
    number_of_shares_outstanding: int
    curr_price: float
    effective_tax_rate: float
    marginal_tax_rate: float
    unlevered_beta: float
    risk_free_rate: float
    equity_risk_premium: float
    mature_erp: float
    pre_tax_cost_of_debt: float
    average_maturity: int
    prob_of_failure: float
    value_of_options: float
    revenue_growth_rate_next_year: float
    operating_margin_next_year: float
    compounded_annual_revenue_growth_rate: float
    target_pre_tax_operating_margin: float
    year_of_convergence_for_margin: int
    years_of_high_growth: int
    sales_to_capital_ratio_early: float
    sales_to_capital_ratio_steady: float
    r_and_d_expenses: list = []
    discount_rate: float = None


app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/py/")
def read_root():
    return {"Status": "OK"}


@app.get("/api/py/history")
def get_history(ticker: str):
    ticker = yf.Ticker(ticker)
    out = ticker.history(period="6mo")["Close"].values
    return {"history": out.tolist()}


@app.post("/api/py/costOfCapital")
def cost_of_capital(request: CostOfCapitalRequest):
    return calc_cost_of_capital(
        request.interest_expense,
        request.pre_tax_cost_of_debt,
        request.average_maturity,
        request.bv_debt,
        request.num_shares_outstanding,
        request.curr_price,
        request.unlevered_beta,
        request.tax_rate,
        request.risk_free_rate,
        request.equity_risk_premium,
    )


@app.post("/api/py/dcf")
def discounted_cash_flow(request: DCFRequest):
    value_per_share, df, cost_of_capital_components, final_components = dcf(
        revenues=request.revenues,
        operating_income=request.operating_income,
        interest_expense=request.interest_expense,
        book_value_of_equity=request.book_value_of_equity,
        book_value_of_debt=request.book_value_of_debt,
        cash_and_marketable_securities=request.cash_and_marketable_securities,
        cross_holdings_and_other_non_operating_assets=request.cross_holdings_and_other_non_operating_assets,
        minority_interest=request.minority_interest,
        number_of_shares_outstanding=request.number_of_shares_outstanding,
        curr_price=request.curr_price,
        effective_tax_rate=request.effective_tax_rate,
        marginal_tax_rate=request.marginal_tax_rate,
        unlevered_beta=request.unlevered_beta,
        risk_free_rate=request.risk_free_rate,
        equity_risk_premium=request.equity_risk_premium,
        mature_erp=request.mature_erp,
        pre_tax_cost_of_debt=request.pre_tax_cost_of_debt,
        average_maturity=request.average_maturity,
        prob_of_failure=request.prob_of_failure,
        value_of_options=request.value_of_options,
        revenue_growth_rate_next_year=request.revenue_growth_rate_next_year,
        operating_margin_next_year=request.operating_margin_next_year,
        compounded_annual_revenue_growth_rate=request.compounded_annual_revenue_growth_rate,
        target_pre_tax_operating_margin=request.target_pre_tax_operating_margin,
        year_of_convergence_for_margin=request.year_of_convergence_for_margin,
        years_of_high_growth=request.years_of_high_growth,
        sales_to_capital_ratio_early=request.sales_to_capital_ratio_early,
        sales_to_capital_ratio_steady=request.sales_to_capital_ratio_steady,
        r_and_d_expenses=request.r_and_d_expenses,
        discount_rate=request.discount_rate,
    )
    df = df.fillna("")
    return {"value_per_share": value_per_share, "df": df.to_dict(orient="records"), "cost_of_capital_components": cost_of_capital_components, "final_components": final_components}

# Export handler for Vercel
handler = app
