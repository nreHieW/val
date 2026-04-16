"use client";

import {
  FinancialComparisonRow,
  METRICS,
  MetricKey,
  formatMetricValue,
  getCellBgColor,
} from "./peerComparisonHelpers";

export default function PeerMetricsTable({
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

  const mainRow =
    rows.find((row) => row.Ticker.toUpperCase() === mainTicker.toUpperCase()) ?? rows[0];

  const visibleMetricDefinitions = METRICS.filter((metric) =>
    visibleMetrics.includes(metric.key),
  );

  const stickyColBase =
    "sticky left-0 min-w-[200px] max-w-[200px] border-r border-border px-3 py-2.5";
  const stickyTh = `${stickyColBase} z-30`;
  const stickyTd = `${stickyColBase} z-20`;
  const stickyShadow =
    "shadow-[6px_0_8px_-4px_hsl(var(--border)/0.6)]";

  return (
    <div className="w-full overflow-x-auto rounded-md border bg-background">
      <table className="w-full min-w-[800px] text-xs">
        <thead>
          <tr className="border-b">
            <th
              className={`${stickyTh} ${stickyShadow} bg-muted text-left font-medium`}
            >
              Company
            </th>
            {visibleMetricDefinitions.map((metric) => (
              <th
                key={metric.key}
                className="whitespace-nowrap bg-muted px-3 py-2.5 text-right font-medium"
              >
                {metric.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
            const isLast = index === rows.length - 1;
            return (
              <tr
                key={row.Ticker}
                className={`transition-colors hover:bg-muted/20 ${isLast ? "" : "border-b"}`}
              >
                <td
                  className={`${stickyTd} ${stickyShadow} ${
                    isMain ? "bg-muted font-semibold" : "bg-background"
                  }`}
                >
                  {row.Ticker}
                  {row.Name ? (
                    <span className="block truncate font-normal text-muted-foreground">
                      {row.Name}
                    </span>
                  ) : null}
                  {row.ttmPeriodEnd ? (
                    <span className="block truncate text-xxs font-normal text-muted-foreground/70">
                      TTM through {row.ttmPeriodEnd}
                    </span>
                  ) : null}
                </td>
                {visibleMetricDefinitions.map((metric) => {
                  const value = row[metric.key];
                  const baseValue = mainRow[metric.key];
                  const bgColor = isMain
                    ? undefined
                    : getCellBgColor(metric.key, value, baseValue, metric.higherIsBetter);

                  return (
                    <td
                      key={`${row.Ticker}-${metric.key}`}
                      className="px-3 py-2.5 text-right tabular-nums"
                      style={bgColor ? { backgroundColor: bgColor } : undefined}
                    >
                      {formatMetricValue(metric.key as MetricKey, value)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
