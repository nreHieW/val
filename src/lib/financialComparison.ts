export type PeRange = { low: number | null; high: number | null };

export type CapitalStructure = {
  cash: number | null;
  debt: number | null;
  equity: number | null;
  cashWeight: number | null;
  debtWeight: number | null;
  equityWeight: number | null;
};

export const METRICS = [
  { key: "pctOf52WeekHigh", label: "% of 52 Week High", format: "percent100" },
  { key: "revenue", label: "Revenue", format: "currency" },
  { key: "netIncome", label: "Net Income", format: "currency" },
  { key: "ebitda", label: "EBITDA", format: "currency" },
  { key: "ebit", label: "EBIT", format: "currency" },
  { key: "netProfitMargin", label: "Net Profit Margin", format: "percent" },
  { key: "operatingMargin", label: "Operating Margin", format: "percent" },
  { key: "ebitdaMargin", label: "EBITDA Margin", format: "percent" },
  { key: "revenueGrowth", label: "Revenue Growth", format: "percent" },
  { key: "ebitdaGrowth", label: "EBITDA Growth", format: "percent" },
  { key: "pe", label: "P/E", format: "number" },
  { key: "forwardPe", label: "Forward P/E", format: "number" },
  { key: "priceToSales", label: "Price/Sales", format: "number" },
  { key: "priceToFcf", label: "Price/FCF", format: "number" },
  { key: "evToEbitda", label: "EV/EBITDA", format: "number" },
  { key: "evToSales", label: "EV/Sales", format: "number" },
  { key: "interestCoverage", label: "Interest Coverage", format: "number" },
  { key: "roic", label: "ROIC", format: "percent" },
  { key: "wacc", label: "WACC", format: "percent" },
  { key: "netDebtToEbitda", label: "Net Debt/EBITDA", format: "number" },
  { key: "epsCurrentYear", label: "EPS Forecast CY", format: "number" },
  { key: "epsNextYear", label: "EPS Forecast NY", format: "number" },
  { key: "forecastRevenueNtm", label: "Revenue Forecast NTM", format: "currency" },
  { key: "forecastRevenueCagr", label: "Revenue CAGR Forecast", format: "percent" },
  { key: "forecastOperatingMargin", label: "Operating Margin Forecast", format: "percent" },
  { key: "salesToCapital", label: "Sales/Capital", format: "number" },
] as const;

export type MetricKey = (typeof METRICS)[number]["key"];
export type MetricDefinition = (typeof METRICS)[number];

export type FinancialComparisonRow = Record<MetricKey, number | null> & {
  Ticker: string;
  Name: string;
  ttmPeriodEnd?: string | null;
  peRange90d: PeRange;
  peRange1y: PeRange;
  capitalStructure: CapitalStructure;
};

function formatCurrency(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (absolute >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (absolute >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(2)}`;
}

export function formatMetricValue(metric: MetricDefinition, value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "-";
  if (metric.format === "currency") return formatCurrency(value);
  if (metric.format === "percent") return `${(value * 100).toFixed(2)}%`;
  if (metric.format === "percent100") return `${value.toFixed(2)}%`;
  return value.toFixed(2);
}

export function formatPeRange(range: PeRange | null | undefined): string {
  if (!range || range.low === null || range.high === null) return "-";
  return `${range.low.toFixed(1)}–${range.high.toFixed(1)}x`;
}
