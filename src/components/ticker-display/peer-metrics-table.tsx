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
      <div className="rounded border border-dashed p-4 text-xs text-muted-foreground">
        No comparison data available for the selected tickers.
      </div>
    );
  }

  const mainRow =
    rows.find((row) => row.Ticker.toUpperCase() === mainTicker.toUpperCase()) ?? rows[0];

  const visibleMetricDefinitions = METRICS.filter((metric) =>
    visibleMetrics.includes(metric.key),
  );
  const companyColumnClass =
    "sticky left-0 z-20 min-w-[220px] max-w-[220px] border-r border-border px-3 py-2";

  return (
    <div className="w-full overflow-x-auto rounded border bg-background pb-5">
      <table className="w-full min-w-[900px] text-xs">
        <thead>
          <tr className="bg-muted/40">
            <th
              className={`${companyColumnClass} bg-background text-left font-medium shadow-[8px_0_12px_-8px_rgba(0,0,0,0.65)]`}
            >
              Company
            </th>
            {visibleMetricDefinitions.map((metric) => (
              <th key={metric.key} className="whitespace-nowrap px-3 py-2 text-right font-medium">
                {metric.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
            return (
              <tr key={row.Ticker} className="border-t">
                <td
                  className={`${companyColumnClass} shadow-[8px_0_12px_-8px_rgba(0,0,0,0.65)] ${
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
                    <span className="block truncate text-[11px] font-normal text-muted-foreground/80">
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
                      className="px-3 py-2 text-right tabular-nums transition-colors"
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
