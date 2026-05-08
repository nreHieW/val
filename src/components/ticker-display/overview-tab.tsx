import { EpsEstimate, TickerOverview } from "./types";

function formatCompactMoney(value: number | null | undefined, decimals = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(decimals)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(decimals)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(decimals)}M`;
  return `$${value.toFixed(decimals)}`;
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  return value.toFixed(decimals);
}

function formatPercent(value: number | null | undefined, decimals = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(decimals)}%`;
}

function formatSignedPercent(value: number | null | undefined, decimals = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(decimals)}%`;
}

function truncateSummary(summary: string | null | undefined) {
  if (!summary) return "No company description is available yet.";
  if (summary.length <= 620) return summary;
  return `${summary.slice(0, 620).trim()}...`;
}

function rangePosition(overview: TickerOverview) {
  const price = overview.market?.price;
  const low = overview.market?.fiftyTwoWeekLow;
  const high = overview.market?.fiftyTwoWeekHigh;
  if (price == null || low == null || high == null || high === low) return null;
  return Math.min(100, Math.max(0, ((price - low) / (high - low)) * 100));
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative";
}) {
  return (
    <div className="min-w-0">
      <p className="text-xxs text-muted-foreground/60">{label}</p>
      <p
        className={`mt-1 truncate text-sm font-medium tabular-nums ${
          tone === "positive"
            ? "text-signal-positive"
            : tone === "negative"
              ? "text-signal-negative"
              : ""
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border/50 px-4 py-4 sm:px-5 sm:py-5">
      <h2 className="text-xs font-medium tracking-tight">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function EpsRow({ label, estimate }: { label: string; estimate?: EpsEstimate | null }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] gap-3 border-b border-border/40 py-2.5 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs tabular-nums">{formatNumber(estimate?.avg)}</span>
      <span className="text-xs tabular-nums text-muted-foreground">
        {formatSignedPercent(estimate?.growth)}
      </span>
    </div>
  );
}

export default function OverviewTab({ overview }: { overview: TickerOverview | null }) {
  if (!overview) {
    return <div className="min-h-[24rem]" />;
  }

  const companyName = overview.profile?.name ?? overview.profile?.shortName ?? overview.Ticker;
  const target = overview.analyst?.targets;
  const targetReference = target?.median ?? target?.mean;
  const upside = overview.analyst?.targetUpside;
  const dayChange = overview.market?.dayChangePercent;
  const rangePct = rangePosition(overview);
  const recommendations = overview.analyst?.recommendations?.current;
  const buyRatings = (recommendations?.strongBuy ?? 0) + (recommendations?.buy ?? 0);
  const totalRatings =
    buyRatings +
    (recommendations?.hold ?? 0) +
    (recommendations?.sell ?? 0) +
    (recommendations?.strongSell ?? 0);

  return (
    <div className="space-y-8 pt-1">
      <header className="grid gap-5 sm:grid-cols-[1fr_auto] sm:items-start">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{overview.Ticker}</p>
          <h1 className="mt-1 text-xl font-medium tracking-tight sm:text-2xl">
            {companyName}
          </h1>
          <p className="mt-2 text-xs text-muted-foreground">
            {[overview.profile?.sector, overview.profile?.industry, overview.profile?.country]
              .filter(Boolean)
              .join(" / ") || "Company profile"}
          </p>
        </div>
        {overview.profile?.website && (
          <a
            href={overview.profile.website}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-muted-foreground underline underline-offset-4 transition-colors hover:text-foreground"
          >
            Company website
          </a>
        )}
      </header>

      <section className="rounded-lg border border-border/50 px-4 py-4 sm:px-5">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Price"
            value={formatCompactMoney(overview.market?.price)}
            tone={dayChange == null ? undefined : dayChange >= 0 ? "positive" : "negative"}
          />
          <Metric label="Market Cap" value={formatCompactMoney(overview.market?.marketCap)} />
          <Metric label="Forward P/E" value={formatNumber(overview.valuation?.forwardPe)} />
          <Metric
            label="Analyst Upside"
            value={formatSignedPercent(upside)}
            tone={upside == null ? undefined : upside >= 0 ? "positive" : "negative"}
          />
        </div>
        <div className="mt-5 grid gap-4 border-t border-border/40 pt-4 sm:grid-cols-3">
          <Metric label="Enterprise Value" value={formatCompactMoney(overview.market?.enterpriseValue)} />
          <Metric label="EV / EBITDA" value={formatNumber(overview.valuation?.enterpriseToEbitda)} />
          <Metric label="Beta" value={formatNumber(overview.market?.beta)} />
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[1.25fr_0.75fr]">
        <Section title="Business">
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
            {truncateSummary(overview.profile?.summary)}
          </p>
          {rangePct != null && (
            <div className="mt-6">
              <div className="mb-2 flex justify-between text-xxs text-muted-foreground/60">
                <span>52-week low {formatCompactMoney(overview.market?.fiftyTwoWeekLow)}</span>
                <span>high {formatCompactMoney(overview.market?.fiftyTwoWeekHigh)}</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-foreground/70"
                  style={{ width: `${rangePct}%` }}
                />
              </div>
            </div>
          )}
        </Section>

        <Section title="Valuation">
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted-foreground">Trailing P/E</dt>
            <dd className="tabular-nums">{formatNumber(overview.valuation?.trailingPe)}</dd>
            <dt className="text-muted-foreground">Forward P/E</dt>
            <dd className="tabular-nums">{formatNumber(overview.valuation?.forwardPe)}</dd>
            <dt className="text-muted-foreground">Price / Sales</dt>
            <dd className="tabular-nums">{formatNumber(overview.valuation?.priceToSales)}</dd>
            <dt className="text-muted-foreground">EV / Revenue</dt>
            <dd className="tabular-nums">{formatNumber(overview.valuation?.enterpriseToRevenue)}</dd>
            <dt className="text-muted-foreground">Operating Margin</dt>
            <dd className="tabular-nums">{formatPercent(overview.valuation?.operatingMargins)}</dd>
          </dl>
        </Section>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section title="Analysts">
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted-foreground">Target Low</dt>
            <dd className="tabular-nums">{formatCompactMoney(target?.low)}</dd>
            <dt className="text-muted-foreground">Target Median</dt>
            <dd className="tabular-nums">{formatCompactMoney(targetReference)}</dd>
            <dt className="text-muted-foreground">Target High</dt>
            <dd className="tabular-nums">{formatCompactMoney(target?.high)}</dd>
            <dt className="text-muted-foreground">Buy Ratings</dt>
            <dd className="tabular-nums">
              {totalRatings ? `${buyRatings}/${totalRatings}` : "-"}
            </dd>
          </dl>
        </Section>

        <Section title="EPS Expectations">
          <div className="grid grid-cols-[1fr_auto_auto] gap-3 pb-1 text-xxs text-muted-foreground/60">
            <span>Period</span>
            <span>Avg EPS</span>
            <span>Growth</span>
          </div>
          <EpsRow label="Current year" estimate={overview.eps?.estimates?.currentYear} />
          <EpsRow label="Next year" estimate={overview.eps?.estimates?.nextYear} />
          <EpsRow label="Current quarter" estimate={overview.eps?.estimates?.currentQuarter} />
        </Section>

        <Section title="Ownership">
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted-foreground">Insider Held</dt>
            <dd className="tabular-nums">{formatPercent(overview.ownership?.insidersPercentHeld)}</dd>
            <dt className="text-muted-foreground">Institution Held</dt>
            <dd className="tabular-nums">{formatPercent(overview.ownership?.institutionsPercentHeld)}</dd>
            <dt className="text-muted-foreground">Institution Count</dt>
            <dd className="tabular-nums">{formatNumber(overview.ownership?.institutionsCount, 0)}</dd>
            <dt className="text-muted-foreground">Insider Roster</dt>
            <dd className="tabular-nums">{overview.ownership?.insiderRoster?.length ?? "-"}</dd>
          </dl>
        </Section>
      </div>
    </div>
  );
}
