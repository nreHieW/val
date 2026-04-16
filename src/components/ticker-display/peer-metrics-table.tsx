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
    <div className="w-full space-y-4">
      {/* Mobile: one card per company — avoids two-axis horizontal scroll */}
      <div className="md:hidden space-y-3">
        {rows.map((row) => {
          const isMain = row.Ticker.toUpperCase() === mainTicker.toUpperCase();
          return (
            <section
              key={row.Ticker}
              className={`rounded-lg border bg-background p-3 ${
                isMain ? "border-foreground/20 bg-muted/40 shadow-sm" : "border-border"
              }`}
              aria-label={`${row.Ticker} metrics`}
            >
              <header className="border-b border-border/60 pb-2.5">
                <p className="text-sm font-semibold leading-tight">{row.Ticker}</p>
                {row.Name ? (
                  <p className="mt-0.5 text-xs text-muted-foreground">{row.Name}</p>
                ) : null}
                {row.ttmPeriodEnd ? (
                  <p className="mt-1 text-xxs text-muted-foreground/80">
                    TTM through {row.ttmPeriodEnd}
                  </p>
                ) : null}
              </header>
              <dl className="divide-y divide-border/50">
                {visibleMetricDefinitions.map((metric) => {
                  const value = row[metric.key];
                  const baseValue = mainRow[metric.key];
                  const bgColor = isMain
                    ? undefined
                    : getCellBgColor(
                        metric.key,
                        value,
                        baseValue,
                        metric.higherIsBetter,
                      );

                  return (
                    <div
                      key={metric.key}
                      className="flex min-h-[44px] items-center justify-between gap-3 py-2"
                      style={bgColor ? { backgroundColor: bgColor } : undefined}
                    >
                      <dt className="max-w-[55%] text-xs leading-snug text-muted-foreground">
                        {metric.label}
                      </dt>
                      <dd className="text-right text-sm tabular-nums">
                        {formatMetricValue(metric.key as MetricKey, value)}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </section>
          );
        })}
      </div>

      <div className="hidden w-full overflow-x-auto rounded-md border bg-background md:block">
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
    </div>
  );
}
