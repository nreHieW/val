import { DcfRow, ReverseDcfOutput } from "@/lib/dcf";
import { DCFInputData, EpsEstimate, TickerOverview } from "./types";

function formatCompactMoney(value: number | null | undefined, decimals = 2) {
  if (value == null || !Number.isFinite(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(decimals)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(decimals)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(decimals)}M`;
  return `$${value.toFixed(decimals)}`;
}

function formatNumber(value: number | null | undefined, decimals = 2) {
  return value == null || !Number.isFinite(value) ? "-" : value.toFixed(decimals);
}

function formatPercent(value: number | null | undefined, decimals = 1) {
  return value == null || !Number.isFinite(value) ? "-" : `${(value * 100).toFixed(decimals)}%`;
}

function formatSignedPercent(value: number | null | undefined, decimals = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(decimals)}%`;
}

function truncateSummary(summary: string | null | undefined) {
  if (!summary) return "No company description is available yet.";
  return summary.length <= 800 ? summary : `${summary.slice(0, 800).trim()}...`;
}

function rangePosition(overview: TickerOverview) {
  const price = overview.market?.price;
  const low = overview.market?.fiftyTwoWeekLow;
  const high = overview.market?.fiftyTwoWeekHigh;
  if (price == null || low == null || high == null || high === low) return null;
  return Math.min(100, Math.max(0, ((price - low) / (high - low)) * 100));
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-medium tabular-nums">{value}</span>
    </div>
  );
}

function FieldList({ rows }: { rows: string[][] }) {
  return (
    <div className="mt-3 divide-y divide-border/30">
      {rows.map(([label, value]) => <DataRow key={label} label={label} value={value} />)}
    </div>
  );
}

function EpsRow({ label, estimate }: { label: string; estimate?: EpsEstimate | null }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="flex items-baseline gap-3">
        <span className="text-xs font-medium tabular-nums">{formatNumber(estimate?.avg)}</span>
        <span className="text-xs tabular-nums text-muted-foreground/60">
          {formatSignedPercent(estimate?.growth)}
        </span>
      </span>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xxs font-medium uppercase tracking-wider text-muted-foreground/50">{children}</h2>;
}

function FieldSection({ title, rows }: { title: string; rows: string[][] }) {
  return (
    <div>
      <SectionHeading>{title}</SectionHeading>
      <FieldList rows={rows} />
    </div>
  );
}

function RatingBar({ buy, hold, sell }: { buy: number; hold: number; sell: number }) {
  const total = buy + hold + sell;
  const bPct = (buy / total) * 100;
  const hPct = (hold / total) * 100;
  return (
    <div className="mt-3 flex h-1.5 w-full overflow-hidden rounded-full">
      <div className="bg-signal-positive transition-all" style={{ width: `${bPct}%` }} />
      <div className="bg-muted-foreground/20 transition-all" style={{ width: `${hPct}%` }} />
      <div className="flex-1 bg-signal-negative/60" />
    </div>
  );
}

export default function OverviewTab({
  overview,
  valuePerShare,
  dcfInputs,
  dcfRows,
  reverseDcf,
}: {
  overview: TickerOverview | null;
  valuePerShare?: number | null;
  dcfInputs?: DCFInputData | null;
  dcfRows?: DcfRow[] | null;
  reverseDcf?: ReverseDcfOutput | null;
}) {
  if (!overview) {
    return (
      <div className="min-h-[24rem] px-1 py-6 text-sm text-muted-foreground">
        No overview data is available for this ticker yet.
      </div>
    );
  }

  const companyName = overview.profile?.name ?? overview.profile?.shortName ?? overview.Ticker;
  const target = overview.analyst?.targets;
  const targetReference = target?.median ?? target?.mean;
  const upside = overview.analyst?.targetUpside;
  const currentPrice = overview.market?.price;
  const rangePct = rangePosition(overview);
  const recommendations = overview.analyst?.recommendations?.current;
  const buyRatings = (recommendations?.strongBuy ?? 0) + (recommendations?.buy ?? 0);
  const holdRatings = recommendations?.hold ?? 0;
  const sellRatings = (recommendations?.sell ?? 0) + (recommendations?.strongSell ?? 0);
  const totalRatings = buyRatings + holdRatings + sellRatings;
  const dcfPct =
    valuePerShare != null && Number.isFinite(valuePerShare) && currentPrice != null && valuePerShare > 0
      ? (currentPrice / valuePerShare) * 100
      : null;
  const keyMetrics = [
    { label: "Mkt Cap", value: formatCompactMoney(overview.market?.marketCap) },
    { label: "EV", value: formatCompactMoney(overview.market?.enterpriseValue) },
    { label: "Fwd P/E", value: formatNumber(overview.valuation?.forwardPe) },
    { label: "EV/EBITDA", value: formatNumber(overview.valuation?.enterpriseToEbitda) },
    { label: "Beta", value: formatNumber(overview.market?.beta) },
    ...(valuePerShare != null && Number.isFinite(valuePerShare)
      ? [
          {
            label: "DCF Value",
            value: `$${valuePerShare.toFixed(2)}`,
            tone: dcfPct == null ? "" : dcfPct > 100 ? "text-signal-negative" : "text-signal-positive",
          },
        ]
      : []),
    {
      label: "Analyst",
      value: formatSignedPercent(upside),
      tone: upside == null ? "" : upside >= 0 ? "text-signal-positive" : "text-signal-negative",
    },
  ];
  const dcfAssumptions = [
    ["Revenue Growth NTM", formatPercent(dcfInputs?.revenue_growth_rate_next_year)],
    ["Revenue CAGR", formatPercent(dcfInputs?.compounded_annual_revenue_growth_rate)],
    ["Operating Margin NTM", formatPercent(dcfInputs?.operating_margin_next_year)],
    ["Target Margin", formatPercent(dcfInputs?.target_pre_tax_operating_margin)],
    ["ROIC", formatPercent(dcfRows?.[1]?.roic)],
  ];
  const valuationRows = [
    ["Trailing P/E", formatNumber(overview.valuation?.trailingPe)],
    ["Forward P/E", formatNumber(overview.valuation?.forwardPe)],
    ["Price / Sales", formatNumber(overview.valuation?.priceToSales)],
    ["EV / Revenue", formatNumber(overview.valuation?.enterpriseToRevenue)],
  ];
  const ownershipRows = [
    ["Insiders", formatPercent(overview.ownership?.insidersPercentHeld)],
    ["Institutions", formatPercent(overview.ownership?.institutionsPercentHeld)],
    ["Institution Count", formatNumber(overview.ownership?.institutionsCount, 0)],
  ];
  const reverseDcfRows = [
    ["Implied Revenue CAGR", formatPercent(reverseDcf?.implied_revenue_cagr.implied_value)],
    ["Margin Held At", formatPercent(dcfInputs?.target_pre_tax_operating_margin)],
  ];

  return (
    <div className="pt-1">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-xxs text-muted-foreground/50">
            {[overview.profile?.sector, overview.profile?.industry, overview.profile?.country]
              .filter(Boolean)
              .join(" · ") || overview.Ticker}
          </p>
          <h1 className="mt-1.5 text-xl font-medium tracking-tight sm:text-2xl">{companyName}</h1>
        </div>

        <div>
          <p className="text-xxs text-muted-foreground/50">Price</p>
          <p className="text-xl font-medium tabular-nums sm:text-2xl">{formatCompactMoney(currentPrice)}</p>
        </div>
      </header>

      <div className="mt-6 flex flex-wrap gap-x-8 gap-y-3 border-y border-border/40 py-4">
        {keyMetrics.map((metric) => (
          <div key={metric.label}>
            <p className="text-xxs text-muted-foreground/50">{metric.label}</p>
            <p className={`text-sm font-medium tabular-nums ${metric.tone ?? ""}`}>{metric.value}</p>
          </div>
        ))}
      </div>

      {rangePct != null && (
        <div className="mt-5">
          <div className="mb-1.5 flex justify-between text-xxs text-muted-foreground/40">
            <span>{formatCompactMoney(overview.market?.fiftyTwoWeekLow)}</span>
            <span>{formatCompactMoney(overview.market?.fiftyTwoWeekHigh)}</span>
          </div>
          <div className="relative h-1 rounded-full bg-muted">
            <div className="absolute left-0 top-0 h-full rounded-full bg-foreground/60" style={{ width: `${rangePct}%` }} />
            <div
              className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground"
              style={{ left: `${rangePct}%` }}
            />
          </div>
          <p className="mt-1 text-center text-xxs text-muted-foreground/40">52-week range</p>
        </div>
      )}

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_auto_1fr]">
        <FieldSection title="DCF Assumptions" rows={dcfAssumptions} />

        <div className="hidden w-px bg-border/40 lg:block" />

        <FieldSection title="Price-Implied Reverse DCF" rows={reverseDcfRows} />
      </div>

      <div className="mt-10 grid gap-8 lg:grid-cols-[3fr_2fr]">
        <FieldSection title="Valuation Multiples" rows={valuationRows} />

        <div>
          <SectionHeading>Analyst Consensus</SectionHeading>
          <div className="mt-4 flex items-baseline justify-between">
            <span className="text-xxs text-muted-foreground">Target</span>
            <span className="text-sm font-medium tabular-nums">{formatCompactMoney(targetReference)}</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between text-xxs text-muted-foreground/60">
            <span>{formatCompactMoney(target?.low)}</span>
            <span>{formatCompactMoney(target?.high)}</span>
          </div>
          {totalRatings > 0 && (
            <>
              <RatingBar buy={buyRatings} hold={holdRatings} sell={sellRatings} />
              <div className="mt-1.5 flex justify-between text-xxs text-muted-foreground/50">
                <span>{buyRatings} buy</span>
                <span>{holdRatings} hold</span>
                <span>{sellRatings} sell</span>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="mt-10 grid gap-8 lg:grid-cols-[2fr_3fr]">
        <FieldSection title="Ownership" rows={ownershipRows} />

        <div>
          <SectionHeading>EPS Estimates</SectionHeading>
          <div className="mt-3 divide-y divide-border/30">
            <EpsRow label="Current year" estimate={overview.eps?.estimates?.currentYear} />
            <EpsRow label="Next year" estimate={overview.eps?.estimates?.nextYear} />
            <EpsRow label="Current quarter" estimate={overview.eps?.estimates?.currentQuarter} />
          </div>
        </div>
      </div>

      <div className="mt-10 border-t border-border/30 pt-6">
        <SectionHeading>About</SectionHeading>
        <p className="mt-3 max-w-3xl text-xs leading-relaxed text-muted-foreground">
          {truncateSummary(overview.profile?.summary)}
        </p>
        {overview.profile?.website && (
          <a
            href={overview.profile.website}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-block text-xxs text-muted-foreground/50 underline underline-offset-4 transition-colors hover:text-foreground"
          >
            {overview.profile.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
          </a>
        )}
      </div>
    </div>
  );
}
