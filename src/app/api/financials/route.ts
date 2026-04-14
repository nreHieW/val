import dbConnect from "../../../lib/dbconnect";
import Financials from "@/app/(models)/Financials";

const MAX_TICKERS = 20;

type FinancialRow = {
  Ticker: string;
  Name: string;
  ttmPeriodEnd: string | null;
  pctOf52WeekHigh: number | null;
  revenue: number | null;
  netIncome: number | null;
  ebitda: number | null;
  ebit: number | null;
  pe: number | null;
  forwardPe: number | null;
  priceToSales: number | null;
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

function getTtmSeries(
  doc: Record<string, unknown>,
  latestKey: string,
  previousKey: string,
): { latest: number | null; previous: number | null } {
  return {
    latest: toFiniteNumber(doc[latestKey]),
    previous: toFiniteNumber(doc[previousKey]),
  };
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
  const revenueSeries = getTtmSeries(doc, "Revenue TTM", "Revenue Prev TTM");
  const netIncomeSeries = getTtmSeries(doc, "Net Income TTM", "Net Income Prev TTM");
  const ebitdaSeries = getTtmSeries(doc, "EBITDA TTM", "EBITDA Prev TTM");
  const ebitSeries = getTtmSeries(doc, "EBIT TTM", "EBIT Prev TTM");

  const price = toFiniteNumber(doc.Price);
  const weekHigh = toFiniteNumber(doc["52-Week High"]);
  const marketCap = toFiniteNumber(doc["Market Cap"]);
  const enterpriseValue = toFiniteNumber(doc["Enterprise Value"]);
  const pe =
    toFiniteNumber(doc["P/E"]) ??
    toFiniteNumber(doc["PE"]) ??
    toFiniteNumber(doc.trailingPE) ??
    ratio(marketCap, netIncomeSeries.latest);
  const forwardPe =
    toFiniteNumber(doc["Forward PE"]) ??
    toFiniteNumber(doc["Forward P/E"]) ??
    toFiniteNumber(doc.forwardPE);
  const priceToSales =
    toFiniteNumber(doc["Price to Sales"]) ??
    toFiniteNumber(doc["Price/Sales"]) ??
    toFiniteNumber(doc.priceToSalesTrailing12Months) ??
    ratio(marketCap, revenueSeries.latest);
  const ttmPeriodEnd = typeof doc["TTM Period End"] === "string" ? doc["TTM Period End"] : null;
  const pctOf52WeekHigh =
    price !== null && weekHigh !== null && weekHigh !== 0
      ? (price / weekHigh) * 100
      : null;

  return {
    Ticker: String(doc.Ticker ?? ""),
    Name: normalizeCompanyName(doc.Name),
    ttmPeriodEnd,
    pctOf52WeekHigh,
    revenue: revenueSeries.latest,
    netIncome: netIncomeSeries.latest,
    ebitda: ebitdaSeries.latest,
    ebit: ebitSeries.latest,
    pe,
    forwardPe,
    priceToSales,
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
