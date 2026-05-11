import type { Metadata } from "next";
import Link from "next/link";
import MainHeader from "@/components/main-header";
import dbConnect from "@/lib/dbconnect";
import Industry from "@/app/(models)/Industry";

export const metadata: Metadata = {
  title: "val: macro dashboard",
  description: "Macro signals and warning signs for market context",
};

export const dynamic = "force-dynamic";

type SignalState = "supportive" | "watch" | "risk" | "unavailable";
type SignalGroup = "primary" | "warning";

type Metric = {
  name: string;
  group: SignalGroup;
  value: string;
  context: string;
  threshold: string;
  source: string;
  sourceUrl: string;
  state: SignalState;
  updated?: string;
  footnote?: string;
};

type IndustryDoc = {
  sector_key?: string;
  sector_name?: string;
  industry_key?: string;
  industry_name?: string;
  symbol?: string;
  market_weight?: number;
  top_companies?: Array<Record<string, unknown>>;
  performance_pct?: Record<string, number | null>;
};

const stateLabel: Record<SignalState, string> = {
  supportive: "supportive",
  watch: "watch",
  risk: "risk",
  unavailable: "waiting",
};

const stateClasses: Record<SignalState, string> = {
  supportive: "border-[oklch(72%_0.13_164)] bg-[oklch(96%_0.025_164)] text-[oklch(39%_0.11_164)] dark:bg-[oklch(22%_0.035_164)] dark:text-[oklch(80%_0.09_164)]",
  watch: "border-[oklch(78%_0.12_78)] bg-[oklch(97%_0.026_78)] text-[oklch(43%_0.095_78)] dark:bg-[oklch(23%_0.032_78)] dark:text-[oklch(82%_0.09_78)]",
  risk: "border-[oklch(72%_0.14_24)] bg-[oklch(96%_0.024_24)] text-[oklch(43%_0.13_24)] dark:bg-[oklch(22%_0.035_24)] dark:text-[oklch(79%_0.1_24)]",
  unavailable: "border-border bg-muted/55 text-muted-foreground",
};

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function fetchText(url: string): Promise<string | null> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    return await response.text();
  } catch {
    return null;
  }
}

function formatDate(value?: number | string | Date) {
  if (!value) return undefined;
  const date = value instanceof Date ? value : typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function formatPercent(value: number, digits = 1) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatMillions(value: number) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}T`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}B`;
  return `$${value.toFixed(0)}M`;
}

function fredSeries(csv: string | null) {
  if (!csv) return [] as Array<{ date: string; value: number }>;
  return csv
    .trim()
    .split("\n")
    .slice(1)
    .map((row) => {
      const [date, raw] = row.split(",");
      const value = Number(raw);
      return date && Number.isFinite(value) ? { date, value } : null;
    })
    .filter((row): row is { date: string; value: number } => Boolean(row));
}

function latestFinite(rows: Array<{ date: string; value: number }>) {
  return rows.length ? rows[rows.length - 1] : null;
}

async function getVix(): Promise<Metric> {
  type YahooChart = { chart?: { result?: { meta?: { regularMarketPrice?: number; regularMarketTime?: number } }[] } };
  const data = await fetchJson<YahooChart>("https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d");
  const meta = data?.chart?.result?.[0]?.meta;
  const value = meta?.regularMarketPrice;

  return {
    name: "VIX above 30",
    group: "primary",
    value: typeof value === "number" ? value.toFixed(1) : "not available",
    threshold: "Supportive when VIX is above 30.",
    context: typeof value === "number" ? (value >= 30 ? "Fear is elevated relative to the normal 15 to 20 range." : "Fear is below the stress level named by the model.") : "Yahoo returned no current VIX quote.",
    source: "Yahoo Finance",
    sourceUrl: "https://finance.yahoo.com/quote/%5EVIX/",
    state: typeof value === "number" ? (value >= 30 ? "supportive" : value >= 25 ? "watch" : "risk") : "unavailable",
    updated: formatDate(meta?.regularMarketTime),
  };
}

async function getFed(): Promise<Metric> {
  const rows = fredSeries(await fetchText("https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"));
  const latest = latestFinite(rows);
  const previous = rows.length > 1 ? rows[rows.length - 2] : null;
  const delta = latest && previous ? latest.value - previous.value : null;

  return {
    name: "Fed not raising rates",
    group: "primary",
    value: latest ? `${latest.value.toFixed(2)}%` : "not available",
    threshold: "Supportive when the latest rate is flat or lower than the prior reading.",
    context: latest && delta !== null ? (Math.abs(delta) <= 0.01 ? "Latest monthly reading is unchanged from the prior month." : delta < 0 ? `Latest monthly reading fell by ${Math.abs(delta).toFixed(2)} pts.` : `Latest monthly reading rose by ${delta.toFixed(2)} pts.`) : "FRED did not return enough observations to compare direction.",
    source: "FRED FEDFUNDS",
    sourceUrl: "https://fred.stlouisfed.org/series/FEDFUNDS",
    state: latest && delta !== null ? (delta <= 0.01 ? "supportive" : "risk") : "unavailable",
    updated: formatDate(latest?.date),
  };
}

async function getFinraMarginDebt(): Promise<Metric> {
  const html = await fetchText("https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics");
  const rows = html
    ? Array.from(html.matchAll(/<tr><td>([^<]+)<\/td><td>([\d,]+)<\/td><td>[\d,]+<\/td><td>[\d,]+<\/td><\/tr>/g)).map((match) => ({
        month: match[1],
        debt: Number(match[2].replace(/,/g, "")),
      }))
    : [];
  const latest = rows[0];
  const previous = rows[1];
  const change = latest && previous ? latest.debt - previous.debt : null;

  return {
    name: "FINRA margin debt declining",
    group: "primary",
    value: latest ? formatMillions(latest.debt) : "not available",
    threshold: "Supportive when the latest released month is below the prior month.",
    context: latest && previous && change !== null ? `${latest.month} debit balances were ${formatMillions(latest.debt)}, ${change < 0 ? "down" : change > 0 ? "up" : "flat"} ${formatMillions(Math.abs(change))} from ${previous.month}. FINRA publishes this with a normal reporting lag.` : "FINRA publishes this series with a normal reporting lag, but the page table could not be read right now.",
    source: "FINRA margin statistics",
    sourceUrl: "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics",
    state: change === null ? "unavailable" : change < 0 ? "supportive" : change === 0 ? "watch" : "risk",
    updated: latest?.month,
    footnote: "Latest released month can trail current market conditions by several weeks.",
  };
}

async function getIndustries() {
  try {
    await dbConnect();
    return (await Industry.find({}, { _id: 0, sector_name: 1, sector_key: 1, industry_name: 1, industry_key: 1, symbol: 1, market_weight: 1, top_companies: 1, performance_pct: 1 }).lean()) as IndustryDoc[];
  } catch {
    return [] as IndustryDoc[];
  }
}

function getReturn(industry: IndustryDoc) {
  const perf = industry.performance_pct ?? {};
  return perf["6mo"] ?? perf["3mo"] ?? perf.ytd ?? null;
}

async function getLeadingIndustrySignal(industries: IndustryDoc[]): Promise<Metric> {
  const ranked = industries
    .map((industry) => ({ ...industry, returnPct: getReturn(industry) }))
    .filter((industry): industry is IndustryDoc & { returnPct: number } => typeof industry.returnPct === "number" && Number.isFinite(industry.returnPct))
    .sort((a, b) => b.returnPct - a.returnPct);
  const leader = ranked[0];
  const runnerUp = ranked[1];
  const gap = leader && runnerUp ? leader.returnPct - runnerUp.returnPct : null;

  return {
    name: "Clear leading industry",
    group: "primary",
    value: leader ? formatPercent(leader.returnPct) : "not populated",
    threshold: "Supportive when one scraped industry leads peers by roughly 5 pts or more.",
    context: leader ? `${leader.industry_name ?? leader.industry_key} leads the populated industry set${leader.sector_name ? ` in ${leader.sector_name}` : ""}${gap !== null ? `, ${gap.toFixed(1)} pts ahead of the next industry` : ""}.` : "The industries scraper has not populated enough ranked records yet.",
    source: "App industries scraper",
    sourceUrl: "#",
    state: gap === null ? "unavailable" : gap >= 5 ? "supportive" : gap >= 2 ? "watch" : "risk",
  };
}

async function getSectorEarningsSignal(industries: IndustryDoc[]): Promise<Metric> {
  const leader = industries
    .map((industry) => ({ ...industry, returnPct: getReturn(industry) }))
    .filter((industry): industry is IndustryDoc & { returnPct: number } => typeof industry.returnPct === "number")
    .sort((a, b) => b.returnPct - a.returnPct)[0];
  const topCompanies = leader?.top_companies?.slice(0, 5) ?? [];
  const names = topCompanies.map((company) => String(company.symbol ?? company.Symbol ?? "")).filter(Boolean);

  return {
    name: "Leader backed by earnings",
    group: "primary",
    value: names.length ? `${names.length} constituents` : "not available",
    threshold: "Supportive only when leading constituents beat EPS and revenue estimates.",
    context: names.length ? `The scraper identifies ${names.join(", ")} as top companies in the leading industry. Estimate beats need a reliable earnings feed before this can be marked supportive.` : "No populated leading-industry constituents are available yet.",
    source: "App industries scraper",
    sourceUrl: "#",
    state: names.length ? "watch" : "unavailable",
    footnote: "No mock earnings-beat data is used.",
  };
}

async function getCreditSpread(): Promise<Metric> {
  const latest = latestFinite(fredSeries(await fetchText("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2")));
  const value = latest?.value;
  return {
    name: "Credit spreads widening",
    group: "warning",
    value: typeof value === "number" ? `${value.toFixed(2)}%` : "not available",
    threshold: "Warning when high-yield spreads move toward stress levels.",
    context: typeof value === "number" ? (value < 6 ? "High-yield stress is contained relative to crisis thresholds." : value < 10 ? "Spreads are elevated enough to watch closely." : "Credit stress is severe and can overpower equity support.") : "FRED did not return the high-yield spread.",
    source: "FRED BofA US HY OAS",
    sourceUrl: "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
    state: typeof value === "number" ? (value < 6 ? "supportive" : value < 10 ? "watch" : "risk") : "unavailable",
    updated: formatDate(latest?.date),
  };
}

async function getCpi(): Promise<Metric> {
  const rows = fredSeries(await fetchText("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"));
  const latest = latestFinite(rows);
  const priorYear = latest ? rows.find((row) => row.date.slice(5) === latest.date.slice(5) && Number(row.date.slice(0, 4)) === Number(latest.date.slice(0, 4)) - 1) : null;
  const value = latest && priorYear ? (latest.value / priorYear.value - 1) * 100 : null;
  return {
    name: "Inflation staying high",
    group: "warning",
    value: typeof value === "number" ? `${value.toFixed(1)}%` : "not available",
    threshold: "Warning when CPI stays materially above the Fed's comfort zone.",
    context: typeof value === "number" ? (value <= 3 ? "Inflation is near a more flexible policy zone." : value <= 4 ? "Inflation is still elevated enough to constrain liquidity support." : "Inflation is high enough to keep policy restrictive.") : "FRED did not return enough CPI observations to calculate year-over-year inflation.",
    source: "FRED CPIAUCSL",
    sourceUrl: "https://fred.stlouisfed.org/series/CPIAUCSL",
    state: typeof value === "number" ? (value <= 3 ? "supportive" : value <= 4 ? "watch" : "risk") : "unavailable",
    updated: formatDate(latest?.date),
  };
}

function getAccountingTrust(): Metric {
  return {
    name: "Reporting trust intact",
    group: "warning",
    value: "no single feed",
    threshold: "Warning when restatements, auditor exits, or enforcement actions undermine reported earnings.",
    context: "This page does not fabricate a trust score. Use SEC filings and company-specific news when earnings quality is part of the thesis.",
    source: "SEC EDGAR",
    sourceUrl: "https://www.sec.gov/edgar/search/",
    state: "watch",
  };
}

function StatusPill({ state }: { state: SignalState }) {
  return <span className={`inline-flex rounded-full border px-2 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.12em] ${stateClasses[state]}`}>{stateLabel[state]}</span>;
}

function MetricRow({ metric, index }: { metric: Metric; index: number }) {
  const source = metric.sourceUrl.startsWith("/") ? (
    <Link className="underline decoration-border underline-offset-4 transition-colors hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring" href={metric.sourceUrl}>{metric.source}</Link>
  ) : (
    <a className="underline decoration-border underline-offset-4 transition-colors hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring" href={metric.sourceUrl} target="_blank" rel="noreferrer">{metric.source}</a>
  );

  return (
    <li className="grid gap-3 border-t border-border/80 py-5 sm:grid-cols-[2.5rem_minmax(0,1fr)_8.5rem] sm:items-start">
      <div className="hidden text-xs tabular-nums text-muted-foreground sm:block">{String(index).padStart(2, "0")}</div>
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold tracking-tight text-foreground">{metric.name}</h3>
          <StatusPill state={metric.state} />
        </div>
        <p className="text-sm leading-6 text-muted-foreground">{metric.context}</p>
        <p className="text-xs leading-5 text-muted-foreground/85">{metric.threshold}</p>
        <p className="text-[0.7rem] leading-5 text-muted-foreground/75">Source: {source}{metric.updated ? `, updated ${metric.updated}` : ""}{metric.footnote ? ` · ${metric.footnote}` : ""}</p>
      </div>
      <div className="text-left sm:text-right">
        <div className="text-2xl font-light tabular-nums tracking-[-0.04em] text-foreground">{metric.value}</div>
      </div>
    </li>
  );
}

function Section({ title, eyebrow, children }: { title: string; eyebrow: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-1">
          <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{eyebrow}</p>
          <h2 className="text-xl font-semibold tracking-[-0.03em] text-foreground">{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

export default async function MacroPage() {
  const industries = await getIndustries();
  const [vix, fed, finra, leadingIndustry, earnings, creditSpread, cpi] = await Promise.all([
    getVix(),
    getFed(),
    getFinraMarginDebt(),
    getLeadingIndustrySignal(industries),
    getSectorEarningsSignal(industries),
    getCreditSpread(),
    getCpi(),
  ]);

  const primary = [vix, fed, finra, leadingIndustry, earnings];
  const warnings = [creditSpread, cpi, getAccountingTrust()];
  const populated = [...primary, ...warnings].filter((metric) => metric.state !== "unavailable").length;
  return (
    <div className="flex min-h-svh flex-col">
      <MainHeader />
      <main className="pb-14 pt-7 sm:pb-20">
        <section className="mb-10 space-y-6 border-b border-border/80 pb-8">
          <div className="space-y-3">
            <p className="text-[0.65rem] font-semibold uppercase tracking-[0.22em] text-muted-foreground">macro signals</p>
            <h1 className="max-w-[13ch] text-4xl font-semibold tracking-[-0.06em] text-foreground sm:text-5xl">Market context, without a verdict.</h1>
            <p className="max-w-[68ch] text-sm leading-6 text-muted-foreground">
              A read-only dashboard for the five primary conditions and three warning signs from the model. It uses scraper data first, public sources where available, and marks missing feeds plainly.
            </p>
          </div>
          <div className="max-w-48 rounded-lg border border-border bg-card/55 p-4">
            <div className="text-2xl font-light tabular-nums tracking-[-0.04em]">{populated}/8</div>
            <div className="mt-1 text-xs text-muted-foreground">signals populated</div>
          </div>
        </section>

        <div className="space-y-12">
          <Section eyebrow="five checks" title="Primary signals">
            <ol>{primary.map((metric, index) => <MetricRow key={metric.name} metric={metric} index={index + 1} />)}</ol>
          </Section>

          <Section eyebrow="three breakers" title="Warning signs">
            <ol>{warnings.map((metric, index) => <MetricRow key={metric.name} metric={metric} index={index + 1} />)}</ol>
          </Section>

        </div>
      </main>
    </div>
  );
}
