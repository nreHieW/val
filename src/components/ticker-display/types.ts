
// Things that users can input/change
export type UserDCFInputs = {
  [key: string]: any;
  revenues: number;
  revenue_growth_rate_next_year: number;
  operating_margin_next_year: number;
  compounded_annual_revenue_growth_rate: number;
  target_pre_tax_operating_margin: number;
  year_of_convergence_for_margin: number;
  discount_rate: number;
  years_of_high_growth: number;
  sales_to_capital_ratio_early: number;
  sales_to_capital_ratio_steady: number;
  prob_of_failure: number;
  value_of_options: number;
  adjust_r_and_d: boolean;
};

export type ForecastContext = {
  consensus_revenues?: Record<string, number>;
  consensus_ebit?: Record<string, number>;
  ms_growth_next_year?: number;
  ms_margin_next_year?: number;
  current_fiscal_year?: string | null;
  next_fiscal_year?: string;
  quarters_reported?: number | null;
  actual_ytd_revenue?: number | null;
  actual_ytd_operating_income?: number | null;
  next_fiscal_year_weight?: number | null;
  bridged_ntm_revenue?: number | null;
  bridged_ntm_operating_income?: number | null;
  rolling_ntm_revenues?: number[];
};

// Types required to create the DCF model
export type DCFInputData = {
  [key: string]: number | undefined | number[];
  revenues: number;
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
  discount_rate: number;
};
