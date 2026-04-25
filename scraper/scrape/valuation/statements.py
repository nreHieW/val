import numpy as np
import pandas as pd


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
