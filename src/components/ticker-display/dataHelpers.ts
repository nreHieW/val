import { BarChartData } from "@/components/stacked-bar-chart";
import {
  encode as msgPackEncode,
  decode as msgPackDecode,
} from "@msgpack/msgpack";
import { DCFInputData, UserDCFInputs } from "./types";
const metrics = [
  "Operating Expenses",
  "Taxes",
  "Reinvestment",
  "Free Cash Flow",
];

export function createIncomeStatementData(data: any[]): BarChartData {
  let dataSlice = data.slice(0, -1);
  let datasets = dataSlice.reduce((acc, item, index) => {
    const { revenues, operating_margin, taxes, reinvestment, fcff } = item;
    const operating_expenses = revenues * (1 - operating_margin);
    if (index === 0) {
      metrics.forEach((metric, idx) => {
        acc.push({
          label: metric,
          data: [],
          borderWidth: 0,
          borderSkipped: false,
        });
      });
    }

    acc[0].data.push(operating_expenses);
    acc[1].data.push(taxes);
    acc[2].data.push(reinvestment);
    acc[3].data.push(fcff);

    return acc;
  }, []);

  let yearLabels = dataSlice.map((_, index) => `Year ${index}`);
  yearLabels[0] = "Base Year";

  return {
    labels: yearLabels,
    datasets: datasets,
  };
}


const DCFInputKeys = [
  'revenues',
  'operating_income',
  'interest_expense',
  'book_value_of_equity',
  'book_value_of_debt',
  'cash_and_marketable_securities',
  'cross_holdings_and_other_non_operating_assets',
  'minority_interest',
  'number_of_shares_outstanding',
  'curr_price',
  'effective_tax_rate',
  'marginal_tax_rate',
  'unlevered_beta',
  'risk_free_rate',
  'equity_risk_premium',
  'mature_erp',
  'pre_tax_cost_of_debt',
  'average_maturity',
  'prob_of_failure',
  'value_of_options',
  'revenue_growth_rate_next_year',
  'operating_margin_next_year',
  'compounded_annual_revenue_growth_rate',
  'target_pre_tax_operating_margin',
  'year_of_convergence_for_margin',
  'years_of_high_growth',
  'sales_to_capital_ratio_early',
  'sales_to_capital_ratio_steady',
  'discount_rate',
];

export function constructModellingData(data: any): DCFInputData {
  const result: Partial<DCFInputData> = {};
  DCFInputKeys.forEach((key) => {
    const v = data[key];
    result[key as keyof DCFInputData] = v != null ? v : 0;
  });
  result.r_and_d_expenses = data.extras?.research_and_development ?? [0];

  return result as DCFInputData;
}


export function preprocessData(data: DCFInputData) {
  const result = { ...data };
  result.r_and_d_expenses = (result.adjust_r_and_d === undefined || result.adjust_r_and_d) ? result.r_and_d_expenses : [];
  return result;
}

export function encodeInputs(inputs: UserDCFInputs): string {
  const buffer = msgPackEncode(inputs);
  return Buffer.from(buffer)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}
export function decodeInputs(encoding: string): UserDCFInputs {
  const base64 = encoding.replace(/-/g, "+").replace(/_/g, "/");
  const buffer = Buffer.from(base64, "base64");
  const data = msgPackDecode(buffer);
  return data as UserDCFInputs;
}

export function formatAmount(
  value: number | null | undefined,
  money: boolean = false
): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  if (Math.abs(value) >= 1e9) {
    return `$${(value / 1e9).toFixed(2)}B`;
  } else if (Math.abs(value) >= 1e6) {
    return `$${(value / 1e6).toFixed(2)}M`;
  } else {
    if (money) {
      return `$${value.toFixed(2)}`;
    } else {
      return `${value.toFixed(2)}%`
    }
  }
}