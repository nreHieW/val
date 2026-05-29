"use client";

import type { ReactNode } from "react";
import {
  FinancialComparisonRow,
  METRICS,
  MetricKey,
  formatMetricValue,
} from "./peerComparisonHelpers";

type MetricDefinition = (typeof METRICS)[number];

type MetricGroup = {
  title: string;
  metrics: MetricKey[];
  variant: "range" | "bar" | "diverging" | "dot";
};

const GROUPS: MetricGroup[] = [
  {
    title: "Market position",
    metrics: ["pctOf52WeekHigh"],
    variant: "range",
  },
  {
    title: "Scale",
    metrics: ["revenue", "netIncome", "ebitda", "ebit"],
    variant: "bar",
  },
  {
    title: "Profitability",
    metrics: ["netProfitMargin", "operatingMargin", "ebitdaMargin"],
    variant: "diverging",
  },
  {
    title: "Growth",
    metrics: ["revenueGrowth", "ebitdaGrowth"],
    variant: "diverging",
  },
  {
    title: "Valuation",
    metrics: ["pe", "forwardPe", "priceToSales", "priceToFcf", "evToEbitda", "evToSales"],
    variant: "dot",
  },
];

const METRIC_DEFINITION_BY_KEY = new Map(METRICS.map((metric) => [metric.key, metric]));

function isFiniteNumber(value: number | null): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function pct(value: number): string {
  return `${Math.max(0, Math.min(100, value)).toFixed(2)}%`;
}

function getMetricValues(rows: FinancialComparisonRow[], metricKey: MetricKey): number[] {
  return rows.map((row) => row[metricKey]).filter(isFiniteNumber);
}

function getDomain(values: number[], forceZero = false): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 1 };
  let min = Math.min(...values);
  let max = Math.max(...values);

  if (forceZero) {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
  }

  if (min === max) {
    const padding = Math.abs(max || 1) * 0.25;
    min -= padding;
    max += padding;
  }

  return { min, max };
}

function valuePosition(value: number, min: number, max: number): number {
  if (max === min) return 50;
  return ((value - min) / (max - min)) * 100;
}

function MetricShell({
  metric,
  children,
  note,
}: {
  metric: MetricDefinition;
  children: ReactNode;
  note?: string;
}) {
  return (
    <article className="rounded-lg border bg-background p-3 sm:p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold tracking-tight">{metric.label}</h4>
        {note ? <span className="text-[0.68rem] text-muted-foreground">{note}</span> : null}
      </div>
      {children}
    </article>
  );
}

function EmptyMetricRows() {
  return <p className="py-4 text-xs text-muted-foreground">No usable values for this metric.</p>;
}

function RangeMetric({
  metric,
  rows,
  mainTicker,
}: {
  metric: MetricDefinition;
  rows: FinancialComparisonRow[];
  mainTicker: string;
}) {
  const values = getMetricValues(rows, metric.key);
  if (values.length === 0) {
    return <MetricShell metric={metric}><EmptyMetricRows /></MetricShell>;
  }

  return (
    <MetricShell metric={metric} note="0 to 100%">
      <div className="space-y-3">
        {rows.map((row) => {
          const value = row[metric.key];
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          const width = isFiniteNumber(value) ? value : 0;
          return (
            <div key={`${metric.key}-${row.Ticker}`} className="grid grid-cols-[4.75rem_1fr_4.5rem] items-center gap-3 text-xs sm:grid-cols-[6rem_1fr_5rem]">
              <CompanyLabel row={row} isMain={isMain} />
              <div className="h-2 rounded-full bg-muted">
                {isFiniteNumber(value) ? (
                  <div
                    className={`h-full rounded-full ${isMain ? "bg-foreground" : "bg-muted-foreground/35"}`}
                    style={{ width: pct(width) }}
                  />
                ) : null}
              </div>
              <ValueLabel metricKey={metric.key} value={value} />
            </div>
          );
        })}
      </div>
    </MetricShell>
  );
}

function BarMetric({
  metric,
  rows,
  mainTicker,
}: {
  metric: MetricDefinition;
  rows: FinancialComparisonRow[];
  mainTicker: string;
}) {
  const values = getMetricValues(rows, metric.key);
  const hasNegative = values.some((value) => value < 0);
  if (values.length === 0) {
    return <MetricShell metric={metric}><EmptyMetricRows /></MetricShell>;
  }

  if (hasNegative) {
    return <DivergingMetric metric={metric} rows={rows} mainTicker={mainTicker} />;
  }

  const max = Math.max(...values, 1);
  return (
    <MetricShell metric={metric}>
      <div className="space-y-3">
        {rows.map((row) => {
          const value = row[metric.key];
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          const width = isFiniteNumber(value) ? (value / max) * 100 : 0;
          return (
            <div key={`${metric.key}-${row.Ticker}`} className="grid grid-cols-[4.75rem_1fr_4.75rem] items-center gap-3 text-xs sm:grid-cols-[6rem_1fr_5.5rem]">
              <CompanyLabel row={row} isMain={isMain} />
              <div className="h-2 rounded-full bg-muted">
                {isFiniteNumber(value) ? (
                  <div
                    className={`h-full rounded-full ${isMain ? "bg-foreground" : "bg-muted-foreground/35"}`}
                    style={{ width: pct(width) }}
                  />
                ) : null}
              </div>
              <ValueLabel metricKey={metric.key} value={value} />
            </div>
          );
        })}
      </div>
    </MetricShell>
  );
}

function DivergingMetric({
  metric,
  rows,
  mainTicker,
}: {
  metric: MetricDefinition;
  rows: FinancialComparisonRow[];
  mainTicker: string;
}) {
  const values = getMetricValues(rows, metric.key);
  if (values.length === 0) {
    return <MetricShell metric={metric}><EmptyMetricRows /></MetricShell>;
  }

  const { min, max } = getDomain(values, true);
  const zero = valuePosition(0, min, max);

  return (
    <MetricShell metric={metric}>
      <div className="space-y-3">
        {rows.map((row) => {
          const value = row[metric.key];
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          const position = isFiniteNumber(value) ? valuePosition(value, min, max) : zero;
          const left = Math.min(position, zero);
          const width = Math.abs(position - zero);
          const isPositive = isFiniteNumber(value) && value >= 0;
          return (
            <div key={`${metric.key}-${row.Ticker}`} className="grid grid-cols-[4.75rem_1fr_4.75rem] items-center gap-3 text-xs sm:grid-cols-[6rem_1fr_5.5rem]">
              <CompanyLabel row={row} isMain={isMain} />
              <div className="relative h-3 rounded-sm bg-muted">
                <div className="absolute top-[-3px] h-[18px] w-px bg-border" style={{ left: pct(zero) }} />
                {isFiniteNumber(value) ? (
                  <div
                    className={`absolute top-1/2 h-2 -translate-y-1/2 rounded-full ${isMain ? "bg-foreground" : isPositive ? "bg-[hsl(var(--signal-positive)/0.62)]" : "bg-[hsl(var(--signal-negative)/0.62)]"}`}
                    style={{ left: pct(left), width: pct(width) }}
                  />
                ) : null}
              </div>
              <ValueLabel metricKey={metric.key} value={value} />
            </div>
          );
        })}
      </div>
    </MetricShell>
  );
}

function DotMetric({
  metric,
  rows,
  mainTicker,
}: {
  metric: MetricDefinition;
  rows: FinancialComparisonRow[];
  mainTicker: string;
}) {
  const values = getMetricValues(rows, metric.key);
  if (values.length === 0) {
    return <MetricShell metric={metric}><EmptyMetricRows /></MetricShell>;
  }

  const { min, max } = getDomain(values, true);
  const peerMedian = median(values);

  return (
    <MetricShell metric={metric} note="lower is cheaper">
      <div className="space-y-3">
        <div className="relative ml-[4.75rem] h-4 sm:ml-[6rem]">
          <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
          {peerMedian !== null ? (
            <div
              className="absolute top-0 h-4 w-px bg-muted-foreground/45"
              style={{ left: pct(valuePosition(peerMedian, min, max)) }}
              title={`Median ${formatMetricValue(metric.key, peerMedian)}`}
            />
          ) : null}
        </div>
        {rows.map((row) => {
          const value = row[metric.key];
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          const canPlot = isFiniteNumber(value);
          const position = canPlot ? valuePosition(value, min, max) : 0;
          return (
            <div key={`${metric.key}-${row.Ticker}`} className="grid grid-cols-[4.75rem_1fr_4.5rem] items-center gap-3 text-xs sm:grid-cols-[6rem_1fr_5rem]">
              <CompanyLabel row={row} isMain={isMain} />
              <div className="relative h-5">
                <div className="absolute left-0 right-0 top-1/2 h-px bg-border" />
                {peerMedian !== null ? (
                  <div className="absolute top-0 h-5 w-px bg-muted-foreground/35" style={{ left: pct(valuePosition(peerMedian, min, max)) }} />
                ) : null}
                {canPlot ? (
                  <div
                    className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-background ${isMain ? "bg-foreground" : "bg-muted-foreground/60"}`}
                    style={{ left: pct(position) }}
                  />
                ) : null}
              </div>
              <ValueLabel metricKey={metric.key} value={value} />
            </div>
          );
        })}
      </div>
    </MetricShell>
  );
}

function CompanyLabel({ row, isMain }: { row: FinancialComparisonRow; isMain: boolean }) {
  return (
    <div className="min-w-0">
      <span className={`block truncate tabular-nums ${isMain ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
        {row.Ticker}
      </span>
    </div>
  );
}

function ValueLabel({ metricKey, value }: { metricKey: MetricKey; value: number | null }) {
  return (
    <span className="text-right text-[0.68rem] tabular-nums text-muted-foreground sm:text-xs">
      {formatMetricValue(metricKey, value)}
    </span>
  );
}

function renderMetricCard(
  variant: MetricGroup["variant"],
  metric: MetricDefinition,
  rows: FinancialComparisonRow[],
  mainTicker: string,
) {
  if (variant === "range") {
    return <RangeMetric key={metric.key} metric={metric} rows={rows} mainTicker={mainTicker} />;
  }
  if (variant === "bar") {
    return <BarMetric key={metric.key} metric={metric} rows={rows} mainTicker={mainTicker} />;
  }
  if (variant === "diverging") {
    return <DivergingMetric key={metric.key} metric={metric} rows={rows} mainTicker={mainTicker} />;
  }
  return <DotMetric key={metric.key} metric={metric} rows={rows} mainTicker={mainTicker} />;
}

export default function PeerComparisonPanels({
  rows,
  mainTicker,
  visibleMetrics,
}: {
  rows: FinancialComparisonRow[];
  mainTicker: string;
  visibleMetrics: MetricKey[];
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed px-4 py-8 text-center text-xs text-muted-foreground">
        Add peer companies above to compare financials.
      </div>
    );
  }

  const visibleMetricSet = new Set(visibleMetrics);
  const visibleGroups = GROUPS.map((group) => ({
    ...group,
    metrics: group.metrics.filter((metric) => visibleMetricSet.has(metric)),
  })).filter((group) => group.metrics.length > 0);

  return (
    <div className="space-y-5">
      {visibleGroups.map((group) => (
        <section key={group.title} className="rounded-xl border bg-card/45 p-3 sm:p-4">
          <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h3 className="text-sm font-semibold tracking-tight text-foreground">{group.title}</h3>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {group.metrics.map((metricKey) => {
              const metric = METRIC_DEFINITION_BY_KEY.get(metricKey);
              return metric ? renderMetricCard(group.variant, metric, rows, mainTicker) : null;
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
