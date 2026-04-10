import dbConnect from "../../../lib/dbconnect";
import Financials from "@/app/(models)/Financials";

const MAX_TICKERS = 20;

type FinancialRow = {
  Ticker: string;
  Name: string;
  pctOf52WeekHigh: number | null;
  revenue: number | null;
  netIncome: number | null;
  ebitda: number | null;
  ebit: number | null;
  netProfitMargin: number | null;
  operatingMargin: number | null;
  ebitdaMargin: number | null;
  revenueGrowth: number | null;
  ebitdaGrowth: number | null;
  evToEbitda: number | null;
  evToSales: number | null;
};

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function unitMultiplier(unit: unknown): number {
  const unitStr = typeof unit === "string" ? unit.toLowerCase() : "";
  if (unitStr.includes("trillion")) return 1e12;
  if (unitStr.includes("billion")) return 1e9;
  if (unitStr.includes("million")) return 1e6;
  if (unitStr.includes("thousand")) return 1e3;
  return 1;
}

function getLatestAndPrevious(
  doc: Record<string, unknown>,
  metricName: string,
): { latest: number | null; previous: number | null } {
  const regex = new RegExp(`^${metricName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s(\\d{4})$`);
  const candidates: Array<{ year: number; value: number }> = [];
  for (const [key, rawValue] of Object.entries(doc)) {
    const match = key.match(regex);
    if (!match) continue;
    const year = Number(match[1]);
    const value = toFiniteNumber(rawValue);
    if (Number.isFinite(year) && value !== null) {
      candidates.push({ year, value });
    }
  }

  candidates.sort((a, b) => b.year - a.year);
  const scale = unitMultiplier(doc.Unit);
  const latest = candidates[0] ? candidates[0].value * scale : null;
  const previous = candidates[1] ? candidates[1].value * scale : null;

  return { latest, previous };
}

function ratio(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null || denominator === 0) {
    return null;
  }
  const value = numerator / denominator;
  return Number.isFinite(value) ? value : null;
}

function growth(latest: number | null, previous: number | null): number | null {
  if (latest === null || previous === null || previous === 0) {
    return null;
  }
  const value = latest / previous - 1;
  return Number.isFinite(value) ? value : null;
}

function normalizeCompanyName(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  const trimmed = value.trim();
  return trimmed === "0" ? "" : trimmed;
}

function mapToComparisonRow(doc: Record<string, unknown>): FinancialRow {
  const revenueSeries = getLatestAndPrevious(doc, "Net sales");
  const netIncomeSeries = getLatestAndPrevious(doc, "Net income");
  const ebitdaSeries = getLatestAndPrevious(doc, "EBITDA");
  const ebitSeries = getLatestAndPrevious(doc, "EBIT");

  const price = toFiniteNumber(doc.Price);
  const weekHigh = toFiniteNumber(doc["52-Week High"]);
  const enterpriseValue = toFiniteNumber(doc["Enterprise Value"]);
  const pctOf52WeekHigh =
    price !== null && weekHigh !== null && weekHigh !== 0
      ? (price / weekHigh) * 100
      : null;

  return {
    Ticker: String(doc.Ticker ?? ""),
    Name: normalizeCompanyName(doc.Name),
    pctOf52WeekHigh,
    revenue: revenueSeries.latest,
    netIncome: netIncomeSeries.latest,
    ebitda: ebitdaSeries.latest,
    ebit: ebitSeries.latest,
    netProfitMargin: ratio(netIncomeSeries.latest, revenueSeries.latest),
    operatingMargin: ratio(ebitSeries.latest, revenueSeries.latest),
    ebitdaMargin: ratio(ebitdaSeries.latest, revenueSeries.latest),
    revenueGrowth: growth(revenueSeries.latest, revenueSeries.previous),
    ebitdaGrowth: growth(ebitdaSeries.latest, ebitdaSeries.previous),
    evToEbitda: ratio(enterpriseValue, ebitdaSeries.latest),
    evToSales: ratio(enterpriseValue, revenueSeries.latest),
  };
}

export async function GET(request: Request) {
  await dbConnect();
  const { searchParams } = new URL(request.url);
  const tickersParam = searchParams.get("tickers")?.trim() ?? "";

  if (!tickersParam) {
    return Response.json([]);
  }

  const tickers = Array.from(
    new Set(
      tickersParam
        .split(",")
        .map((ticker) => ticker.trim().toUpperCase())
        .filter(Boolean),
    ),
  ).slice(0, MAX_TICKERS);

  if (tickers.length === 0) {
    return Response.json([]);
  }

  const docs = (await Financials.find(
    { Ticker: { $in: tickers } },
    { _id: 0 },
  ).lean()) as Record<string, unknown>[];

  const byTicker = new Map<string, Record<string, unknown>>();
  docs.forEach((doc) => {
    const ticker = String(doc.Ticker ?? "").toUpperCase();
    if (ticker) {
      byTicker.set(ticker, doc);
    }
  });

  const rows = tickers
    .map((ticker) => byTicker.get(ticker))
    .filter((doc): doc is Record<string, unknown> => Boolean(doc))
    .map(mapToComparisonRow);

  return Response.json(rows);
}
