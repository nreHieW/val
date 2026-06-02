export type CostOfCapitalComponents = {
  cost_of_debt: number;
  cost_of_equity: number;
  levered_beta: number;
  risk_free_rate: number;
  equity_risk_premium: number;
};

export type DcfFinalComponents = {
  present_value_of_cash_flows: number;
  book_value_of_debt: number;
  cash_and_marketable_securities: number;
  cross_holdings_and_other_non_operating_assets: number;
  minority_interest: number;
};

export type DcfInput = {
  revenues: number;
  operating_income: number;
  interest_expense: number;
  book_value_of_equity: number;
  book_value_of_debt: number;
  cash_and_marketable_securities: number;
  cross_holdings_and_other_non_operating_assets: number;
  minority_interest: number;
  number_of_shares_outstanding: number;
  curr_price: number;
  effective_tax_rate: number;
  marginal_tax_rate: number;
  unlevered_beta: number;
  risk_free_rate: number;
  equity_risk_premium: number;
  mature_erp: number;
  pre_tax_cost_of_debt: number;
  average_maturity: number;
  prob_of_failure: number;
  value_of_options: number;
  revenue_growth_rate_next_year: number;
  operating_margin_next_year: number;
  compounded_annual_revenue_growth_rate: number;
  target_pre_tax_operating_margin: number;
  year_of_convergence_for_margin: number;
  years_of_high_growth: number;
  sales_to_capital_ratio_early: number;
  sales_to_capital_ratio_steady: number;
  r_and_d_expenses: number[];
  discount_rate?: number | null;
  revenue_growth_rates?: number[] | null;
};

export type DcfRow = {
  revenue_growth_rate: number;
  revenues: number;
  operating_margin: number;
  operating_income: number;
  tax_rate: number;
  taxes: number;
  nol: number;
  nol_cumulative: number;
  nol_utilized: number;
  ebit_after_tax: number;
  reinvestment: number;
  invested_capital: number;
  roic: number;
  cost_of_capital: number;
  fcff: number;
  discount_factor: number;
  pv_fcff: number;
};

export type DcfOutput = {
  value_per_share: number;
  df: DcfRow[];
  cost_of_capital_components: CostOfCapitalComponents;
  final_components: DcfFinalComponents;
};

export type ReverseDcfScenario = {
  implied_value: number | null;
  validation_value_per_share: number | null;
  validation_error: number | null;
};

export type ReverseDcfOutput = {
  target_price: number;
  implied_revenue_cagr: ReverseDcfScenario;
};

function linspace(start: number, end: number, count: number): number[] {
  if (count <= 0) return [];
  if (count === 1) return [start];
  const step = (end - start) / (count - 1);
  return Array.from({ length: count }, (_, i) => start + i * step);
}

function cumsum(values: number[]): number[] {
  let running = 0;
  return values.map((value) => {
    running += value;
    return running;
  });
}

function cumprod(values: number[]): number[] {
  let running = 1;
  return values.map((value) => {
    running *= value;
    return running;
  });
}

function shift(values: number[], periods: number): number[] {
  if (periods <= 0) {
    return [...values];
  }
  return Array.from({ length: values.length }, (_, i) => {
    if (i < periods) return Number.NaN;
    return values[i - periods];
  });
}

function diffNegativeOne(values: number[]): number[] {
  return values.map((value, index) => {
    if (index === values.length - 1) return Number.NaN;
    return value - values[index + 1];
  });
}

function sumRange(values: number[], startIndex: number, endIndexInclusive: number): number {
  let total = 0;
  for (let i = startIndex; i <= endIndexInclusive; i += 1) {
    total += values[i];
  }
  return total;
}

export function calcCostOfCapital(
  interest_expense: number,
  pre_tax_cost_of_debt: number,
  average_maturity: number,
  bv_debt: number,
  num_shares_outstanding: number,
  curr_price: number,
  unlevered_beta: number,
  tax_rate: number,
  risk_free_rate: number,
  equity_risk_premium: number,
): [number, CostOfCapitalComponents] {
  const market_value_of_debt =
    (interest_expense *
      (1 - 1 / (1 + pre_tax_cost_of_debt) ** average_maturity)) /
      pre_tax_cost_of_debt +
    bv_debt / (1 + pre_tax_cost_of_debt) ** average_maturity;
  const market_value_of_equity = num_shares_outstanding * curr_price;
  const market_value_of_capital = market_value_of_debt + market_value_of_equity;
  const equity_weight = market_value_of_equity / market_value_of_capital;
  const debt_weight = market_value_of_debt / market_value_of_capital;

  const levered_beta =
    unlevered_beta *
    (1 + (1 - tax_rate) * (market_value_of_debt / market_value_of_equity));

  const cost_of_debt = pre_tax_cost_of_debt * (1 - tax_rate);
  const cost_of_equity = risk_free_rate + levered_beta * equity_risk_premium;
  const cost_of_capital =
    cost_of_debt * debt_weight + cost_of_equity * equity_weight;

  return [
    cost_of_capital,
    {
      cost_of_debt,
      cost_of_equity,
      levered_beta,
      risk_free_rate,
      equity_risk_premium,
    },
  ];
}

export function rAndDAdjustment(expenses: number[]): [number, number] {
  const num_years = expenses.length - 1;
  const unamortized_weights = linspace(1, 0, num_years + 1);

  const unamortized_amount = unamortized_weights.reduce(
    (sum, weight, index) => sum + weight * expenses[index],
    0,
  );
  const amortization_this_year = expenses
    .slice(1)
    .reduce((sum, value) => sum + value / num_years, 0);
  const adjustment = expenses[0] - amortization_this_year;
  return [adjustment, unamortized_amount];
}

export function dcf(input: DcfInput): DcfOutput {
  const {
    interest_expense,
    pre_tax_cost_of_debt,
    average_maturity,
    book_value_of_debt,
    number_of_shares_outstanding,
    curr_price,
    unlevered_beta,
    marginal_tax_rate,
    risk_free_rate,
    equity_risk_premium,
  } = input;

  let revenues = input.revenues + 1e-8;
  let operating_income = input.operating_income;

  let [start_cost_of_capital, cost_of_capital_components] = calcCostOfCapital(
    interest_expense,
    pre_tax_cost_of_debt,
    average_maturity,
    book_value_of_debt,
    number_of_shares_outstanding,
    curr_price,
    unlevered_beta,
    marginal_tax_rate,
    risk_free_rate,
    equity_risk_premium,
  );

  if (input.discount_rate && input.discount_rate !== 0) {
    start_cost_of_capital = input.discount_rate;
  }

  let value_of_research_asset = 0;
  if (input.r_and_d_expenses.length > 0) {
    const [r_and_d_adjustment_value, research_asset] = rAndDAdjustment(
      input.r_and_d_expenses,
    );
    operating_income += r_and_d_adjustment_value;
    value_of_research_asset = research_asset;
  }

  const defaultRevenueGrowthRates = [
    0,
    input.revenue_growth_rate_next_year,
    ...Array(Math.max(input.years_of_high_growth - 2, 0)).fill(
      input.compounded_annual_revenue_growth_rate,
    ),
    ...linspace(
      input.compounded_annual_revenue_growth_rate,
      risk_free_rate,
      10 - input.years_of_high_growth + 1,
    ),
    risk_free_rate,
  ];
  const revenue_growth_rates = input.revenue_growth_rates ?? defaultRevenueGrowthRates;

  const revenues_factors = revenue_growth_rates.map((x) => 1 + x);
  const projected_revenues = cumprod(revenues_factors).map((x) => x * revenues);

  const starting_operating_margin = operating_income / revenues;
  const operating_margin = [
    starting_operating_margin,
    ...linspace(
      input.operating_margin_next_year,
      input.target_pre_tax_operating_margin,
      input.year_of_convergence_for_margin,
    ),
    ...Array(Math.max(11 - input.year_of_convergence_for_margin, 0)).fill(
      input.target_pre_tax_operating_margin,
    ),
  ];

  const operating_income_series = projected_revenues.map(
    (value, index) => value * operating_margin[index],
  );

  const tax_rate = [
    ...Array(6).fill(input.effective_tax_rate),
    ...linspace(input.effective_tax_rate, input.marginal_tax_rate, 5),
    input.marginal_tax_rate,
  ];

  const taxes = operating_income_series.map((value, index) =>
    value > 0 ? value * tax_rate[index] : 0,
  );
  const nol = operating_income_series.map((value) => (value < 0 ? -value * 0.8 : 0));
  const nol_cumulative = cumsum(nol);
  const nol_utilized = operating_income_series.map((value, index) => {
    if (value > 0) {
      return Math.min(nol_cumulative[index], value);
    }
    return 0;
  });
  const nol_cumulative_after_use = nol_cumulative.map(
    (value, index) => value - nol_utilized[index],
  );
  const taxes_after_nol = taxes.map(
    (value, index) => value - nol_utilized[index] * tax_rate[index],
  );

  const ebit_after_tax = operating_income_series.map(
    (value, index) => value - taxes_after_nol[index],
  );

  const sales_to_capital = [
    ...linspace(input.sales_to_capital_ratio_early, input.sales_to_capital_ratio_steady, 7),
    ...Array(5).fill(input.sales_to_capital_ratio_steady),
  ];
  const reinvestment = diffNegativeOne(projected_revenues).map(
    (value, index) => (-value) / sales_to_capital[index],
  );
  reinvestment[0] = 0;

  const starting_invested_capital =
    input.book_value_of_equity +
    input.book_value_of_debt -
    input.cash_and_marketable_securities +
    value_of_research_asset;
  const invested_capital = cumsum(reinvestment).map(
    (value) => starting_invested_capital + value,
  );
  const roic = ebit_after_tax.map((value, index) => value / invested_capital[index]);

  const end_cost_of_capital = risk_free_rate + input.mature_erp;
  const cost_of_capital = [
    ...Array(6).fill(start_cost_of_capital),
    ...linspace(start_cost_of_capital, end_cost_of_capital, 6),
  ];
  roic[11] = end_cost_of_capital;
  reinvestment[11] = (risk_free_rate / roic[11]) * ebit_after_tax[11];

  const fcff = ebit_after_tax.map((value, index) => value - reinvestment[index]);
  const discount_factor = shift(
    cumprod(cost_of_capital.map((value) => 1 / (1 + value))),
    1,
  );
  const pv_fcff = fcff.map((value, index) => value * discount_factor[index]);

  const terminal_val = fcff[11] / (end_cost_of_capital - risk_free_rate);
  const terminal_pv = terminal_val * discount_factor[10];
  const pv_cf = sumRange(pv_fcff, 1, 11) + terminal_pv;

  const proceeds_if_fail = pv_cf * 0.5;
  const op_value =
    pv_cf * (1 - input.prob_of_failure) + proceeds_if_fail * input.prob_of_failure;
  let value_of_equity =
    op_value -
    input.book_value_of_debt -
    input.minority_interest +
    input.cash_and_marketable_securities +
    input.cross_holdings_and_other_non_operating_assets;
  value_of_equity -= input.value_of_options;
  const value_per_share = value_of_equity / input.number_of_shares_outstanding;

  const df: DcfRow[] = Array.from({ length: 12 }, (_, index) => ({
    revenue_growth_rate: revenue_growth_rates[index],
    revenues: projected_revenues[index],
    operating_margin: operating_margin[index],
    operating_income: operating_income_series[index],
    tax_rate: tax_rate[index],
    taxes: taxes_after_nol[index],
    nol: nol[index],
    nol_cumulative: nol_cumulative_after_use[index],
    nol_utilized: nol_utilized[index],
    ebit_after_tax: ebit_after_tax[index],
    reinvestment: reinvestment[index],
    invested_capital: invested_capital[index],
    roic: roic[index],
    cost_of_capital: cost_of_capital[index],
    fcff: fcff[index],
    discount_factor: discount_factor[index],
    pv_fcff: pv_fcff[index],
  }));

  return {
    value_per_share,
    df,
    cost_of_capital_components,
    final_components: {
      present_value_of_cash_flows: pv_cf,
      book_value_of_debt: input.book_value_of_debt,
      cash_and_marketable_securities: input.cash_and_marketable_securities,
      cross_holdings_and_other_non_operating_assets:
        input.cross_holdings_and_other_non_operating_assets,
      minority_interest: input.minority_interest,
    },
  };
}

const REVERSE_DCF_MIN_CAGR = -0.95;
const REVERSE_DCF_MAX_CAGR = 1.5;
const REVERSE_DCF_TOLERANCE = 1e-8;

function valuePerShareAtRevenueGrowth(input: DcfInput, growthRate: number) {
  return dcf({
    ...input,
    revenue_growth_rate_next_year: growthRate,
    compounded_annual_revenue_growth_rate: growthRate,
  }).value_per_share;
}

function solveImpliedRevenueCagr(input: DcfInput): ReverseDcfScenario {
  const targetPrice = input.curr_price;
  const diffAt = (growthRate: number) => valuePerShareAtRevenueGrowth(input, growthRate) - targetPrice;
  const scenario = (implied_value: number | null): ReverseDcfScenario => {
    if (implied_value == null) {
      return { implied_value: null, validation_value_per_share: null, validation_error: null };
    }

    const validation_value_per_share = valuePerShareAtRevenueGrowth(input, implied_value);
    return {
      implied_value,
      validation_value_per_share,
      validation_error: validation_value_per_share - targetPrice,
    };
  };

  let low = REVERSE_DCF_MIN_CAGR;
  let high = REVERSE_DCF_MAX_CAGR;
  let lowDiff = diffAt(low);
  const highDiff = diffAt(high);

  if (Math.abs(lowDiff) <= REVERSE_DCF_TOLERANCE) return scenario(low);
  if (Math.abs(highDiff) <= REVERSE_DCF_TOLERANCE) return scenario(high);
  if (lowDiff * highDiff > 0) return scenario(null);

  for (let i = 0; i < 100; i += 1) {
    const mid = (low + high) / 2;
    const midDiff = diffAt(mid);

    if (Math.abs(midDiff) <= REVERSE_DCF_TOLERANCE) return scenario(mid);

    if (lowDiff * midDiff <= 0) {
      high = mid;
    } else {
      low = mid;
      lowDiff = midDiff;
    }
  }

  return scenario((low + high) / 2);
}

export function reverseDcf(input: DcfInput): ReverseDcfOutput {
  return {
    target_price: input.curr_price,
    implied_revenue_cagr: solveImpliedRevenueCagr(input),
  };
}

export function fillNaNWithEmptyString(df: DcfRow[]): Array<Record<string, number | string>> {
  return df.map((row) =>
    Object.fromEntries(
      Object.entries(row).map(([key, value]) => [
        key,
        Number.isNaN(value) ? "" : value,
      ]),
    ),
  );
}
