"use client";

import type { ReactNode } from "react";
import {
  FinancialComparisonRow,
  METRICS,
  MetricDefinition,
  MetricKey,
  PeRange,
  formatMetricValue,
  formatPeRange,
} from "@/lib/financialComparison";

type Variant = "range" | "bar" | "diverging" | "dot";
type MetricGroup = { title: string; metrics: MetricKey[]; variant: Variant };
type Domain = { min: number; max: number };

const GROUPS: MetricGroup[] = [
  { title: "Market Position", metrics: ["pctOf52WeekHigh"], variant: "range" },
  { title: "Scale", metrics: ["revenue", "netIncome", "ebitda", "ebit"], variant: "bar" },
  { title: "Profitability", metrics: ["netProfitMargin", "operatingMargin", "ebitdaMargin", "roic"], variant: "diverging" },
  {
    title: "Growth & Forecasts",
    metrics: ["revenueGrowth", "ebitdaGrowth", "forecastRevenueNtm", "forecastRevenueCagr", "forecastOperatingMargin", "epsCurrentYear", "epsNextYear"],
    variant: "diverging",
  },
  { title: "Valuation", metrics: ["pe", "forwardPe", "priceToSales", "priceToFcf", "evToEbitda", "evToSales"], variant: "dot" },
  { title: "Leverage & Efficiency", metrics: ["interestCoverage", "wacc", "netDebtToEbitda", "salesToCapital"], variant: "dot" },
];

const METRIC_BY_KEY = new Map(METRICS.map((metric) => [metric.key, metric]));
const PE_RANGES = [
  { title: "90-Day Range", getRange: (row: FinancialComparisonRow) => row.peRange90d },
  { title: "1-Year Range", getRange: (row: FinancialComparisonRow) => row.peRange1y },
];
const CAPITAL_LEGEND = [
  ["Cash", "bg-muted-foreground/20"],
  ["Debt", "bg-muted-foreground/50"],
  ["Equity", "bg-foreground"],
];

const isNumber = (value: number | null): value is number => typeof value === "number" && Number.isFinite(value);
const pct = (value: number) => `${Math.max(0, Math.min(100, value)).toFixed(2)}%`;
const metricValues = (rows: FinancialComparisonRow[], key: MetricKey) => rows.map((row) => row[key]).filter(isNumber);
const position = (value: number, { min, max }: Domain) => (min === max ? 50 : ((value - min) / (max - min)) * 100);

function domain(values: number[], forceZero = false): Domain {
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (forceZero) {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
  }
  if (min === max) {
    const pad = Math.abs(max || 1) * 0.25;
    min -= pad;
    max += pad;
  }
  return { min, max };
}

function SectionHeading({ children }: { children: ReactNode }) {
  return <h3 className="text-xxs font-medium uppercase tracking-wider text-muted-foreground/50">{children}</h3>;
}

function MetricLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 mt-6 first:mt-0">
      <h4 className="text-xs font-medium text-foreground">{children}</h4>
    </div>
  );
}

function EmptyMetric({ children }: { children: ReactNode }) {
  return (
    <>
      <MetricLabel>{children}</MetricLabel>
      <p className="py-2 text-xxs text-muted-foreground/40">No data available</p>
    </>
  );
}

function CompanyRow({
  row,
  mainTicker,
  value,
  children,
  className = "grid-cols-[4.5rem_1fr_4.5rem] sm:grid-cols-[5.5rem_1fr_5rem]",
}: {
  row: FinancialComparisonRow;
  mainTicker: string;
  value: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
  return (
    <div className={`grid ${className} items-center gap-3 py-1.5 text-xs`}>
      <span className={`truncate tabular-nums ${isMain ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
        {row.Ticker}
      </span>
      {children}
      <span className="text-right text-xxs tabular-nums text-muted-foreground">{value}</span>
    </div>
  );
}

function MetricRow({
  row,
  mainTicker,
  metric,
  valueDomain,
  zero,
  variant,
}: {
  row: FinancialComparisonRow;
  mainTicker: string;
  metric: MetricDefinition;
  valueDomain: Domain;
  zero: number;
  variant: Variant;
}) {
  const value = row[metric.key];
  const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
  const plotted = isNumber(value);
  let chart: ReactNode;

  if (variant === "dot") {
    chart = (
      <div className="relative h-4">
        <div className="absolute inset-x-0 top-1/2 h-px bg-border/40" />
        {plotted && (
          <div
            className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ${isMain ? "bg-foreground" : "bg-muted-foreground/40"}`}
            style={{ left: pct(position(value, valueDomain)) }}
          />
        )}
      </div>
    );
  } else if (variant === "diverging") {
    const valuePos = plotted ? position(value, valueDomain) : zero;
    chart = (
      <div className="relative h-2 rounded-sm bg-muted/50">
        <div className="absolute top-[-2px] h-[16px] w-px bg-border/60" style={{ left: pct(zero) }} />
        {plotted && (
          <div
            className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full ${isMain ? "bg-foreground" : "bg-muted-foreground/40"}`}
            style={{ left: pct(Math.min(valuePos, zero)), width: pct(Math.abs(valuePos - zero)) }}
          />
        )}
      </div>
    );
  } else {
    const width = plotted ? (variant === "range" ? value : (value / valueDomain.max) * 100) : 0;
    chart = (
      <div className="h-1.5 rounded-full bg-muted/50">
        {plotted && (
          <div
            className={`h-full rounded-full ${isMain ? "bg-foreground" : "bg-muted-foreground/30"}`}
            style={{ width: pct(width) }}
          />
        )}
      </div>
    );
  }

  return <CompanyRow row={row} mainTicker={mainTicker} value={formatMetricValue(metric, value)}>{chart}</CompanyRow>;
}

function MetricBlock({
  metric,
  variant,
  rows,
  mainTicker,
}: {
  metric: MetricDefinition;
  variant: Variant;
  rows: FinancialComparisonRow[];
  mainTicker: string;
}) {
  const values = metricValues(rows, metric.key);
  if (!values.length) return <EmptyMetric>{metric.label}</EmptyMetric>;

  const effectiveVariant = variant === "bar" && values.some((value) => value < 0) ? "diverging" : variant;
  const valueDomain =
    effectiveVariant === "range"
      ? { min: 0, max: 100 }
      : effectiveVariant === "bar"
        ? { min: 0, max: Math.max(...values, 1) }
        : domain(values, effectiveVariant !== "dot" || values.some((value) => value < 0));
  const zero = position(0, valueDomain);

  return (
    <>
      <MetricLabel>{metric.label}</MetricLabel>
      <div className="divide-y divide-border/20">
        {rows.map((row) => (
          <MetricRow key={row.Ticker} row={row} mainTicker={mainTicker} metric={metric} valueDomain={valueDomain} zero={zero} variant={effectiveVariant} />
        ))}
      </div>
    </>
  );
}

function PeRangeBlock({
  title,
  getRange,
  rows,
  mainTicker,
}: {
  title: string;
  getRange: (row: FinancialComparisonRow) => PeRange;
  rows: FinancialComparisonRow[];
  mainTicker: string;
}) {
  const ranges = rows.map(getRange).filter((range): range is { low: number; high: number } => isNumber(range.low) && isNumber(range.high));
  if (!ranges.length) return <EmptyMetric>{title}</EmptyMetric>;

  const rangeDomain = {
    min: Math.min(...ranges.map((range) => range.low)),
    max: Math.max(...ranges.map((range) => range.high)),
  };

  return (
    <>
      <MetricLabel>{title}</MetricLabel>
      <div className="divide-y divide-border/20">
        {rows.map((row) => {
          const range = getRange(row);
          const hasRange = range.low !== null && range.high !== null;
          const left = hasRange ? position(range.low!, rangeDomain) : 0;
          const right = hasRange ? position(range.high!, rangeDomain) : left;
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          return (
            <CompanyRow
              key={row.Ticker}
              row={row}
              mainTicker={mainTicker}
              value={formatPeRange(range)}
              className="grid-cols-[4.5rem_1fr_5.5rem] sm:grid-cols-[5.5rem_1fr_6rem]"
            >
              <div className="relative h-4">
                <div className="absolute inset-x-0 top-1/2 h-px bg-border/40" />
                {hasRange && (
                  <div
                    className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full ${isMain ? "bg-foreground" : "bg-muted-foreground/30"}`}
                    style={{ left: pct(left), width: pct(right - left) }}
                  />
                )}
              </div>
            </CompanyRow>
          );
        })}
      </div>
    </>
  );
}

function CapitalStructureBlock({ rows, mainTicker }: { rows: FinancialComparisonRow[]; mainTicker: string }) {
  const hasData = rows.some((row) =>
    [row.capitalStructure.cashWeight, row.capitalStructure.debtWeight, row.capitalStructure.equityWeight].some(isNumber),
  );
  if (!hasData) return <EmptyMetric>Capital Structure</EmptyMetric>;

  return (
    <>
      <MetricLabel>Capital Structure</MetricLabel>
      <div className="mb-2 flex gap-5 text-xxs text-muted-foreground/40">
        {CAPITAL_LEGEND.map(([label, color]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${color}`} /> {label}
          </span>
        ))}
      </div>
      <div className="divide-y divide-border/20">
        {rows.map((row) => {
          const { cashWeight, debtWeight, equityWeight } = row.capitalStructure;
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          const hasRowData = [cashWeight, debtWeight, equityWeight].some(isNumber);
          return (
            <CompanyRow key={row.Ticker} row={row} mainTicker={mainTicker} value={hasRowData ? `${((debtWeight ?? 0) * 100).toFixed(0)}% debt` : "-"}>
              <div className="flex h-1.5 overflow-hidden rounded-full bg-muted/30">
                {hasRowData && (
                  <>
                    <div className="bg-muted-foreground/20" style={{ width: pct((cashWeight ?? 0) * 100) }} />
                    <div className="bg-muted-foreground/50" style={{ width: pct((debtWeight ?? 0) * 100) }} />
                    <div className={isMain ? "bg-foreground" : "bg-foreground/50"} style={{ width: pct((equityWeight ?? 0) * 100) }} />
                  </>
                )}
              </div>
            </CompanyRow>
          );
        })}
      </div>
    </>
  );
}

export default function PeerComparisonPanels({ rows, mainTicker }: { rows: FinancialComparisonRow[]; mainTicker: string }) {
  if (!rows.length) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-muted-foreground/60">Add peer companies to compare financials</p>
        <p className="mt-1 text-xxs text-muted-foreground/30">Use the search above or select from suggested peers</p>
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <section>
        <SectionHeading>Historical P/E Range</SectionHeading>
        <div className="mt-4 grid gap-8 lg:grid-cols-2">
          {PE_RANGES.map(({ title, getRange }) => (
            <div key={title}>
              <PeRangeBlock title={title} getRange={getRange} rows={rows} mainTicker={mainTicker} />
            </div>
          ))}
        </div>
      </section>

      <div className="h-px bg-border/30" />

      {GROUPS.map((group, index) => (
        <section key={group.title}>
          <SectionHeading>{group.title}</SectionHeading>
          <div className="mt-4 grid gap-x-12 gap-y-2 lg:grid-cols-2">
            {group.metrics.map((metricKey) => {
              const metric = METRIC_BY_KEY.get(metricKey);
              return metric ? (
                <div key={metric.key}>
                  <MetricBlock metric={metric} variant={group.variant} rows={rows} mainTicker={mainTicker} />
                </div>
              ) : null;
            })}
          </div>
          {index < GROUPS.length - 1 && <div className="mt-10 h-px bg-border/30" />}
        </section>
      ))}

      <div className="h-px bg-border/30" />

      <section>
        <SectionHeading>Balance Sheet</SectionHeading>
        <div className="mt-4">
          <CapitalStructureBlock rows={rows} mainTicker={mainTicker} />
        </div>
      </section>
    </div>
  );
}
