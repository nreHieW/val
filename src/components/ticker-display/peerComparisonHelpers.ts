export type MetricKey =
  | "pctOf52WeekHigh"
  | "revenue"
  | "netIncome"
  | "ebitda"
  | "ebit"
  | "netProfitMargin"
  | "operatingMargin"
  | "ebitdaMargin"
  | "revenueGrowth"
  | "ebitdaGrowth"
  | "evToEbitda"
  | "evToSales";

export type FinancialComparisonRow = {
  Ticker: string;
  Name: string;
  ttmPeriodEnd?: string | null;
  pctOf52WeekHigh: number | null;
  revenue: number | null;
  netIncome: number | null;
  ebitda: number | null;
  ebit: number | null;
  netProfitMargin: number | null;
  operatingMargin: number | null;
  ebitdaMargin: number | null;
  revenueGrowth: number | null;
  ebitdaGrowth: number | null;
  evToEbitda: number | null;
  evToSales: number | null;
};

export const METRICS: Array<{ key: MetricKey; label: string; higherIsBetter: boolean }> = [
  { key: "pctOf52WeekHigh", label: "% of 52 Week High", higherIsBetter: false },
  { key: "revenue", label: "Revenue", higherIsBetter: true },
  { key: "netIncome", label: "Net Income", higherIsBetter: true },
  { key: "ebitda", label: "EBITDA", higherIsBetter: true },
  { key: "ebit", label: "EBIT", higherIsBetter: true },
  { key: "netProfitMargin", label: "Net Profit Margin", higherIsBetter: true },
  { key: "operatingMargin", label: "Operating Margin", higherIsBetter: true },
  { key: "ebitdaMargin", label: "EBITDA Margin", higherIsBetter: true },
  { key: "revenueGrowth", label: "Revenue Growth", higherIsBetter: true },
  { key: "ebitdaGrowth", label: "EBITDA Growth", higherIsBetter: true },
  { key: "evToEbitda", label: "EV/EBITDA", higherIsBetter: false },
  { key: "evToSales", label: "EV/Sales", higherIsBetter: false },
];

const PERCENT_METRICS: MetricKey[] = [
  "pctOf52WeekHigh",
  "netProfitMargin",
  "operatingMargin",
  "ebitdaMargin",
  "revenueGrowth",
  "ebitdaGrowth",
];

const CURRENCY_METRICS: MetricKey[] = ["revenue", "netIncome", "ebitda", "ebit"];

export function formatMetricValue(key: MetricKey, value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "-";

  if (PERCENT_METRICS.includes(key)) {
    const pctValue = key === "pctOf52WeekHigh" ? value : value * 100;
    return `${pctValue.toFixed(2)}%`;
  }

  if (CURRENCY_METRICS.includes(key)) {
    const absolute = Math.abs(value);
    if (absolute >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (absolute >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (absolute >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    return `$${value.toFixed(2)}`;
  }

  return value.toFixed(2);
}

export function getCellBgColor(
  key: MetricKey,
  value: number | null,
  baseValue: number | null,
  higherIsBetter: boolean,
): string | undefined {
  if (
    value === null ||
    baseValue === null ||
    !Number.isFinite(value) ||
    !Number.isFinite(baseValue) ||
    value === baseValue
  ) {
    return undefined;
  }

  const baseline = Math.abs(baseValue) < 1e-6 ? 1 : Math.abs(baseValue);
  const normalizedDiff = Math.min(Math.abs((value - baseValue) / baseline), 1);
  const alpha = 0.22 + normalizedDiff * 0.38;
  const isValuationMultiple = key === "evToEbitda" || key === "evToSales";
  const better = isValuationMultiple && (!higherIsBetter || key === "evToEbitda" || key === "evToSales")
    ? value > 0 && (baseValue <= 0 || value < baseValue)
    : higherIsBetter
      ? value > baseValue
      : value < baseValue;

  return better
    ? `rgba(22, 163, 74, ${alpha.toFixed(3)})`
    : `rgba(220, 38, 38, ${alpha.toFixed(3)})`;
}
