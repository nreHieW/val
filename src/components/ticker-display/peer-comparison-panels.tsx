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
type MetricGroup = {
  title: string;
  metrics: MetricKey[];
  variant: Variant;
  className?: string;
  metricGridClassName?: string;
};
type Domain = { min: number; max: number };

const GROUPS: MetricGroup[] = [
  { title: "Scale", metrics: ["revenue", "netIncome", "ebitda", "ebit"], variant: "bar", className: "xl:col-span-6" },
  { title: "Profitability", metrics: ["netProfitMargin", "operatingMargin", "ebitdaMargin", "roic"], variant: "diverging", className: "xl:col-span-6" },
  {
    title: "Growth & Forecasts",
    metrics: ["revenueGrowth", "ebitdaGrowth", "forecastRevenueNtm", "forecastRevenueCagr", "epsCurrentYear", "epsNextYear"],
    variant: "diverging",
    className: "xl:col-span-12",
    metricGridClassName: "xl:grid xl:grid-cols-2 xl:gap-x-4 xl:[&>*:nth-child(2)]:border-t-0 xl:[&>*:nth-child(2)]:pt-0",
  },
];

const VALUATION_GROUPS: MetricGroup[] = [
  {
    title: "Valuation",
    metrics: ["pe", "forwardPe", "priceToSales", "priceToFcf", "evToEbitda", "evToSales"],
    variant: "dot",
    className: "xl:col-span-12",
    metricGridClassName: "xl:grid xl:grid-cols-2 xl:gap-x-4 xl:[&>*:nth-child(2)]:border-t-0 xl:[&>*:nth-child(2)]:pt-0",
  },
  {
    title: "Leverage & Efficiency",
    metrics: ["interestCoverage", "wacc", "netDebtToEbitda", "salesToCapital"],
    variant: "dot",
    className: "xl:col-span-12",
    metricGridClassName: "xl:grid xl:grid-cols-2 xl:gap-x-4 xl:[&>*:nth-child(2)]:border-t-0 xl:[&>*:nth-child(2)]:pt-0",
  },
];

const METRIC_BY_KEY = new Map(METRICS.map((metric) => [metric.key, metric]));
const PE_RANGES = [
  { title: "90-Day Range", getRange: (row: FinancialComparisonRow) => row.peRange90d },
  { title: "1-Year Range", getRange: (row: FinancialComparisonRow) => row.peRange1y },
];
const CAPITAL_SEGMENTS = [
  { key: "cash", label: "Cash", barClass: "bg-muted-foreground/25", dotClass: "bg-muted-foreground/25" },
  { key: "debt", label: "Debt", barClass: "bg-muted-foreground/50", dotClass: "bg-muted-foreground/50" },
  { key: "equity", label: "Equity", barClass: "bg-muted-foreground/75", dotClass: "bg-muted-foreground/75" },
] as const;

const ROW_GRID =
  "grid grid-cols-[minmax(3rem,3.75rem)_minmax(0,1fr)_minmax(3.75rem,5rem)] items-center gap-x-3";
const PANEL = "rounded-lg border border-border/60 bg-background px-3 pb-1.5 pt-2 sm:px-4";
const CHART_FILL = "bg-muted-foreground/40";

const isNumber = (value: number | null): value is number => typeof value === "number" && Number.isFinite(value);
const pct = (value: number) => `${Math.max(0, Math.min(100, value)).toFixed(2)}%`;
const metricValues = (rows: FinancialComparisonRow[], key: MetricKey) => rows.map((row) => row[key]).filter(isNumber);
const position = (value: number, { min, max }: Domain) => (min === max ? 50 : ((value - min) / (max - min)) * 100);

function formatCompactCurrency(value: number | null): string {
  if (!isNumber(value)) return "-";
  const absolute = Math.abs(value);
  if (absolute >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (absolute >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (absolute >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${value.toFixed(0)}`;
}

function formatWeight(value: number | null): string {
  return isNumber(value) ? `${(value * 100).toFixed(0)}%` : "-";
}

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
  return (
    <h3 className="text-xxs font-medium uppercase tracking-wider text-muted-foreground">
      {children}
    </h3>
  );
}

function PeerRow({
  row,
  value,
  children,
  className = ROW_GRID,
  valueClassName = "",
}: {
  row: FinancialComparisonRow;
  value: ReactNode;
  children: ReactNode;
  className?: string;
  valueClassName?: string;
}) {
  return (
    <div className={`${className} group py-1`}>
      <span className="truncate text-xxs tabular-nums text-muted-foreground sm:text-xs">{row.Ticker}</span>
      <div className="min-w-0">{children}</div>
      <span className={`whitespace-nowrap text-right text-xxs tabular-nums text-muted-foreground sm:text-xs ${valueClassName}`}>{value}</span>
    </div>
  );
}

function ChartTrack({ children }: { children: ReactNode }) {
  return <div className="relative h-4 w-full">{children}</div>;
}

function DotChart({ value, valueDomain }: { value: number; valueDomain: Domain }) {
  return (
    <ChartTrack>
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
      <div
        className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={{ left: pct(position(value, valueDomain)) }}
      >
        <span className="block h-2 w-2 shrink-0 rounded-full bg-muted-foreground/45" />
      </div>
    </ChartTrack>
  );
}

function DivergingChart({ value, valueDomain, zero }: { value: number; valueDomain: Domain; zero: number }) {
  const valuePos = position(value, valueDomain);

  return (
    <ChartTrack>
      <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-sm bg-muted/35" />
      <div className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-muted-foreground/35" style={{ left: pct(zero) }} />
      <div
        className={`absolute top-1/2 h-2 -translate-y-1/2 rounded-full ${CHART_FILL}`}
        style={{ left: pct(Math.min(valuePos, zero)), width: pct(Math.abs(valuePos - zero)) }}
      />
    </ChartTrack>
  );
}

function BarChart({ widthPct }: { widthPct: number }) {
  return (
    <div className="h-2 rounded-full bg-muted/35">
      <div className={`h-full rounded-full ${CHART_FILL}`} style={{ width: pct(widthPct) }} />
    </div>
  );
}

function MetricChart({
  row,
  metric,
  variant,
  valueDomain,
  zero,
}: {
  row: FinancialComparisonRow;
  metric: MetricDefinition;
  variant: Variant;
  valueDomain: Domain;
  zero: number;
}) {
  const value = row[metric.key];

  if (!isNumber(value)) {
    return <div className="h-4 rounded-sm bg-muted/20" />;
  }

  if (variant === "dot") {
    return <DotChart value={value} valueDomain={valueDomain} />;
  }

  if (variant === "diverging") {
    return <DivergingChart value={value} valueDomain={valueDomain} zero={zero} />;
  }

  const width = variant === "range" ? value : (value / valueDomain.max) * 100;
  return <BarChart widthPct={width} />;
}

function MetricBlock({
  metric,
  variant,
  rows,
}: {
  metric: MetricDefinition;
  variant: Variant;
  rows: FinancialComparisonRow[];
}) {
  const values = metricValues(rows, metric.key);
  if (!values.length) {
    return (
      <div className="border-t border-border/25 py-3 first:border-t-0 first:pt-0">
        <h4 className="text-xs font-medium text-foreground">{metric.label}</h4>
        <p className="mt-1.5 text-xxs text-muted-foreground/50">No data available</p>
      </div>
    );
  }

  const effectiveVariant = variant === "bar" && values.some((value) => value < 0) ? "diverging" : variant;
  const valueDomain =
    effectiveVariant === "range"
      ? { min: 0, max: 100 }
      : effectiveVariant === "bar"
        ? { min: 0, max: Math.max(...values, 1) }
        : domain(values, effectiveVariant !== "dot" || values.some((value) => value < 0));
  const zero = position(0, valueDomain);

  return (
    <div className="border-t border-border/25 py-3 first:border-t-0 first:pt-0">
      <h4 className="mb-2 text-xs font-medium text-foreground/90">{metric.label}</h4>

      <div>
        {rows.map((row) => (
          <PeerRow key={row.Ticker} row={row} value={formatMetricValue(metric, row[metric.key])}>
            <MetricChart
              row={row}
              metric={metric}
              variant={effectiveVariant}
              valueDomain={valueDomain}
              zero={zero}
            />
          </PeerRow>
        ))}
      </div>
    </div>
  );
}

function MetricGroupPanel({ group, rows }: { group: MetricGroup; rows: FinancialComparisonRow[] }) {
  return (
    <section className={group.className}>
      <SectionHeading>{group.title}</SectionHeading>
      <div className={`mt-3 ${PANEL}`}>
        <div className={group.metricGridClassName}>
          {group.metrics.map((metricKey) => {
            const metric = METRIC_BY_KEY.get(metricKey);
            if (!metric) return null;
            return <MetricBlock key={metric.key} metric={metric} variant={group.variant} rows={rows} />;
          })}
        </div>
      </div>
    </section>
  );
}

function PeRangeBlock({
  title,
  getRange,
  rows,
}: {
  title: string;
  getRange: (row: FinancialComparisonRow) => PeRange;
  rows: FinancialComparisonRow[];
}) {
  const ranges = rows.map(getRange).filter((range): range is { low: number; high: number } => isNumber(range.low) && isNumber(range.high));
  if (!ranges.length) {
    return (
      <div>
        <h4 className="text-xs font-medium text-foreground">{title}</h4>
        <p className="mt-1.5 text-xxs text-muted-foreground/50">No data available</p>
      </div>
    );
  }

  const rangeDomain = {
    min: Math.min(...ranges.map((range) => range.low)),
    max: Math.max(...ranges.map((range) => range.high)),
  };

  return (
    <div className={PANEL}>
      <h4 className="mb-2 text-xs font-medium text-foreground">{title}</h4>
      <div>
        {rows.map((row) => {
          const range = getRange(row);
          const hasRange = range.low !== null && range.high !== null;
          const left = hasRange ? position(range.low!, rangeDomain) : 0;
          const right = hasRange ? position(range.high!, rangeDomain) : left;

          return (
            <PeerRow
              key={row.Ticker}
              row={row}
              value={formatPeRange(range)}
              className="grid grid-cols-[minmax(3rem,3.75rem)_minmax(2rem,1fr)_max-content] items-center gap-x-3"
              valueClassName="tracking-tight"
            >
              <ChartTrack>
                <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
                {hasRange && (
                  <div
                    className={`absolute top-1/2 h-2 -translate-y-1/2 rounded-full ${CHART_FILL}`}
                    style={{ left: pct(left), width: pct(right - left) }}
                  />
                )}
              </ChartTrack>
            </PeerRow>
          );
        })}
      </div>
    </div>
  );
}

function CapitalStructureBlock({ rows, className = "" }: { rows: FinancialComparisonRow[]; className?: string }) {
  const hasData = rows.some((row) =>
    [row.capitalStructure.cashWeight, row.capitalStructure.debtWeight, row.capitalStructure.equityWeight].some(isNumber),
  );

  if (!hasData) {
    return <p className={`mt-1.5 text-xxs text-muted-foreground/50 ${className}`}>No data available</p>;
  }

  return (
    <div className={`${PANEL} ${className}`}>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-0.5 text-xxs text-muted-foreground/50">
        {CAPITAL_SEGMENTS.map((segment) => (
          <span key={segment.key} className="inline-flex items-center gap-1">
            <span className={`h-1.5 w-1.5 rounded-full ${segment.dotClass}`} />
            {segment.label}
          </span>
        ))}
      </div>

      <div>
        {rows.map((row) => {
          const { cash, debt, equity, cashWeight, debtWeight, equityWeight } = row.capitalStructure;
          const hasRowData = [cashWeight, debtWeight, equityWeight].some(isNumber);
          const segments = [
            { ...CAPITAL_SEGMENTS[0], amount: cash, weight: cashWeight },
            { ...CAPITAL_SEGMENTS[1], amount: debt, weight: debtWeight },
            { ...CAPITAL_SEGMENTS[2], amount: equity, weight: equityWeight },
          ];
          return (
            <div key={row.Ticker} className="group relative grid grid-cols-[minmax(3rem,3.75rem)_minmax(0,1fr)] items-center gap-x-3 py-1">
              <span className="truncate text-xxs tabular-nums text-muted-foreground sm:text-xs">{row.Ticker}</span>

              <div className="flex h-2.5 overflow-hidden rounded-full bg-muted/30 ring-1 ring-border/25">
                {hasRowData ? (
                  segments.map((segment) => (
                    <div
                      key={segment.key}
                      className={segment.barClass}
                      style={{ width: pct((segment.weight ?? 0) * 100) }}
                    />
                  ))
                ) : (
                  <div className="h-full w-full bg-muted/20" />
                )}
              </div>

              {hasRowData && (
                <div className="pointer-events-none absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-md border border-border/70 bg-background px-2.5 py-1.5 text-xxs text-muted-foreground opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100">
                  <div className="flex gap-2.5 tabular-nums">
                    {segments.map((segment) => (
                      <span key={segment.key} className="whitespace-nowrap">
                        <span className="text-foreground/70">{segment.label}</span> {formatWeight(segment.weight)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function PeerComparisonPanels({ rows }: { rows: FinancialComparisonRow[] }) {
  if (!rows.length) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-muted-foreground/60">Add peer companies to compare financials</p>
        <p className="mt-1 text-xxs text-muted-foreground/30">Use the search above or select from suggested peers</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-6">
      <div className="grid items-stretch gap-4 lg:grid-cols-2">
        <section className="flex flex-col">
          <SectionHeading>Market Position</SectionHeading>
          <div className={`mt-3 ${PANEL} flex-1`}>
            <MetricBlock metric={METRIC_BY_KEY.get("pctOf52WeekHigh")!} variant="range" rows={rows} />
          </div>
        </section>

        <section className="flex flex-col">
          <SectionHeading>Balance Sheet</SectionHeading>
          <div className="mt-3 flex flex-1 flex-col">
            <CapitalStructureBlock rows={rows} className="flex-1" />
          </div>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-12">
        {GROUPS.map((group) => (
          <MetricGroupPanel key={group.title} group={group} rows={rows} />
        ))}
      </div>

      <section>
        <SectionHeading>Historical P/E Range</SectionHeading>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {PE_RANGES.map(({ title, getRange }) => (
            <PeRangeBlock key={title} title={title} getRange={getRange} rows={rows} />
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-12">
        {VALUATION_GROUPS.map((group) => (
          <MetricGroupPanel key={group.title} group={group} rows={rows} />
        ))}
      </div>
    </div>
  );
}
