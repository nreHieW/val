import json
from pathlib import Path

import numpy as np

from modelling import calc_cost_of_capital, dcf, r_and_d_adjustment


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def to_jsonable(value):
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def generate_cost_of_capital_fixtures():
    cases = [
        {
            "name": "baseline",
            "inputs": {
                "interest_expense": 320_000_000.0,
                "pre_tax_cost_of_debt": 0.052,
                "average_maturity": 6,
                "bv_debt": 9_800_000_000.0,
                "num_shares_outstanding": 980_000_000,
                "curr_price": 172.4,
                "unlevered_beta": 1.08,
                "tax_rate": 0.21,
                "risk_free_rate": 0.041,
                "equity_risk_premium": 0.048,
            },
        },
        {
            "name": "higher_leverage",
            "inputs": {
                "interest_expense": 980_000_000.0,
                "pre_tax_cost_of_debt": 0.081,
                "average_maturity": 8,
                "bv_debt": 27_000_000_000.0,
                "num_shares_outstanding": 620_000_000,
                "curr_price": 81.7,
                "unlevered_beta": 0.92,
                "tax_rate": 0.25,
                "risk_free_rate": 0.038,
                "equity_risk_premium": 0.061,
            },
        },
        {
            "name": "low_debt_profile",
            "inputs": {
                "interest_expense": 40_000_000.0,
                "pre_tax_cost_of_debt": 0.034,
                "average_maturity": 4,
                "bv_debt": 1_200_000_000.0,
                "num_shares_outstanding": 2_100_000_000,
                "curr_price": 55.2,
                "unlevered_beta": 1.15,
                "tax_rate": 0.19,
                "risk_free_rate": 0.037,
                "equity_risk_premium": 0.05,
            },
        },
    ]

    out = []
    for case in cases:
        coc, components = calc_cost_of_capital(**case["inputs"])
        out.append(
            {
                "name": case["name"],
                "inputs": case["inputs"],
                "output": {
                    "cost_of_capital": to_jsonable(coc),
                    "components": to_jsonable(components),
                },
            }
        )
    return {"cases": out}


def generate_r_and_d_fixtures():
    cases = [
        {"name": "five_year_history", "expenses": [520.0, 470.0, 420.0, 390.0, 350.0, 310.0]},
        {"name": "declining_spend", "expenses": [180.0, 160.0, 145.0, 130.0]},
        {"name": "flat_spend", "expenses": [100.0, 100.0, 100.0, 100.0, 100.0]},
        {"name": "minimal_valid_length", "expenses": [120.0, 70.0]},
    ]
    out = []
    for case in cases:
        adjustment, unamortized = r_and_d_adjustment(case["expenses"])
        out.append(
            {
                "name": case["name"],
                "expenses": case["expenses"],
                "output": {
                    "adjustment": to_jsonable(adjustment),
                    "unamortized_amount": to_jsonable(unamortized),
                },
            }
        )
    return {"cases": out}


def dcf_base_inputs():
    return {
        "revenues": 18_400_000_000.0,
        "operating_income": 3_250_000_000.0,
        "interest_expense": 360_000_000.0,
        "book_value_of_equity": 14_200_000_000.0,
        "book_value_of_debt": 9_600_000_000.0,
        "cash_and_marketable_securities": 2_400_000_000.0,
        "cross_holdings_and_other_non_operating_assets": 470_000_000.0,
        "minority_interest": 210_000_000.0,
        "number_of_shares_outstanding": 840_000_000,
        "curr_price": 132.5,
        "effective_tax_rate": 0.185,
        "marginal_tax_rate": 0.21,
        "unlevered_beta": 1.04,
        "risk_free_rate": 0.039,
        "equity_risk_premium": 0.052,
        "mature_erp": 0.043,
        "pre_tax_cost_of_debt": 0.056,
        "average_maturity": 6,
        "prob_of_failure": 0.05,
        "value_of_options": 170_000_000.0,
        "revenue_growth_rate_next_year": 0.081,
        "operating_margin_next_year": 0.181,
        "compounded_annual_revenue_growth_rate": 0.067,
        "target_pre_tax_operating_margin": 0.194,
        "year_of_convergence_for_margin": 5,
        "years_of_high_growth": 6,
        "sales_to_capital_ratio_early": 1.6,
        "sales_to_capital_ratio_steady": 1.22,
        "r_and_d_expenses": [620_000_000.0, 580_000_000.0, 530_000_000.0, 490_000_000.0, 450_000_000.0, 410_000_000.0],
        "discount_rate": 0,
    }


def generate_dcf_fixtures():
    base = dcf_base_inputs()
    cases = [
        {"name": "baseline", "inputs": base},
        {"name": "no_r_and_d_adjustment", "inputs": {**base, "r_and_d_expenses": []}},
        {"name": "negative_operating_income", "inputs": {**base, "operating_income": -480_000_000.0, "operating_margin_next_year": 0.01, "target_pre_tax_operating_margin": 0.12}},
        {"name": "discount_rate_override", "inputs": {**base, "discount_rate": 0.091}},
        {"name": "growth_margin_boundaries", "inputs": {**base, "years_of_high_growth": 2, "year_of_convergence_for_margin": 1, "revenue_growth_rate_next_year": 0.12, "compounded_annual_revenue_growth_rate": 0.085}},
    ]

    out = []
    for case in cases:
        value_per_share, df, cost_of_capital_components, final_components = dcf(**case["inputs"])
        df_records = df.fillna("").to_dict(orient="records")
        out.append(
            {
                "name": case["name"],
                "inputs": to_jsonable(case["inputs"]),
                "output": {
                    "value_per_share": to_jsonable(value_per_share),
                    "df": to_jsonable(df_records),
                    "cost_of_capital_components": to_jsonable(cost_of_capital_components),
                    "final_components": to_jsonable(final_components),
                },
            }
        )
    return {"cases": out}


def main():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = {
        "calc_cost_of_capital": generate_cost_of_capital_fixtures(),
        "r_and_d_adjustment": generate_r_and_d_fixtures(),
        "dcf": generate_dcf_fixtures(),
    }

    for name, payload in fixtures.items():
        out_path = FIXTURES_DIR / f"{name}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
