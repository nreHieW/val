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

  return (
    <div className="w-full overflow-x-auto rounded border">
      <table className="w-full min-w-[900px] text-xs">
        <thead>
          <tr className="bg-muted/40">
            <th className="sticky left-0 z-10 bg-muted/70 px-3 py-2 text-left font-medium">
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
                  className={`sticky left-0 z-10 px-3 py-2 ${
                    isMain ? "bg-muted/70 font-semibold" : "bg-background"
                  }`}
                >
                  {row.Ticker}
                  {row.Name ? (
                    <span className="block max-w-[230px] truncate font-normal text-muted-foreground">
                      {row.Name}
                    </span>
                  ) : null}
                </td>
                {visibleMetricDefinitions.map((metric) => {
                  const value = row[metric.key];
                  const baseValue = mainRow[metric.key];
                  const bgColor = isMain
                    ? undefined
                    : getCellBgColor(value, baseValue, metric.higherIsBetter);

                  return (
                    <td
                      key={`${row.Ticker}-${metric.key}`}
                      className="px-3 py-2 text-right tabular-nums"
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
