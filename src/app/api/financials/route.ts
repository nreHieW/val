import DCFInput from "@/app/(models)/DcfInputs";
import Financials from "@/app/(models)/Financials";
import TickerOverview from "@/app/(models)/TickerOverview";
import { FinancialComparisonRow } from "@/lib/financialComparison";
import { calcCostOfCapital } from "@/lib/dcf";
import dbConnect from "../../../lib/dbconnect";

const MAX_TICKERS = 20;
type Doc = Record<string, unknown>;
type NullableNumber = number | null;

function toFiniteNumber(value: unknown): NullableNumber {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;

  const parsed = Number(value.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function ratio(numerator: NullableNumber, denominator: NullableNumber): NullableNumber {
  if (numerator === null || denominator === null || denominator === 0) return null;

  const value = numerator / denominator;
  return Number.isFinite(value) ? value : null;
}

function growth(latest: NullableNumber, previous: NullableNumber): NullableNumber {
  return latest === null || previous === null ? null : ratio(latest - previous, previous);
}

function normalizeCompanyName(value: unknown): string {
  if (typeof value !== "string") return "";
  const trimmed = value.trim();
  return trimmed === "0" ? "" : trimmed;
}

function ttm(doc: Doc, latestKey: string, previousKey: string) {
  return {
    latest: toFiniteNumber(doc[latestKey]),
    previous: toFiniteNumber(doc[previousKey]),
  };
}

function numberAt(doc: Doc | undefined, ...path: string[]): NullableNumber {
  let value: unknown = doc;
  for (const key of path) value = (value as Doc | undefined)?.[key];
  return toFiniteNumber(value);
}

function nonZero(value: NullableNumber): NullableNumber {
  return value !== null && Number.isFinite(value) && value !== 0 ? value : null;
}

function historicalPeRange(
  closes: number[],
  currentPrice: NullableNumber,
  currentPe: NullableNumber,
  days: number,
) {
  if (currentPrice === null || currentPrice === 0 || currentPe === null) {
    return { low: null, high: null };
  }

  const values = closes
    .slice(-days)
    .map((close) => currentPe * (close / currentPrice))
    .filter((value) => Number.isFinite(value) && value > 0);

  return values.length
    ? { low: Math.min(...values), high: Math.max(...values) }
    : { low: null, high: null };
}

function capitalStructure(cash: NullableNumber, debt: NullableNumber, equity: NullableNumber) {
  const positiveCash = Math.max(cash ?? 0, 0);
  const positiveDebt = Math.max(debt ?? 0, 0);
  const positiveEquity = Math.max(equity ?? 0, 0);
  const total = positiveCash + positiveDebt + positiveEquity;

  return {
    cash,
    debt,
    equity,
    cashWeight: total ? positiveCash / total : null,
    debtWeight: total ? positiveDebt / total : null,
    equityWeight: total ? positiveEquity / total : null,
  };
}

function forecastRevenue(dcf: Doc | undefined, revenue: NullableNumber) {
  if (!dcf || dcf.revenue_growth_rate_next_year === undefined || revenue === null) return null;
  return toFiniteNumber(revenue * (1 + (toFiniteNumber(dcf.revenue_growth_rate_next_year) ?? 0)));
}

function wacc(dcf: Doc | undefined): NullableNumber {
  const discountRate = toFiniteNumber(dcf?.discount_rate);
  if (discountRate !== null) return discountRate;

  const values = [
    "interest_expense",
    "pre_tax_cost_of_debt",
    "average_maturity",
    "book_value_of_debt",
    "number_of_shares_outstanding",
    "curr_price",
    "unlevered_beta",
    "marginal_tax_rate",
    "risk_free_rate",
    "equity_risk_premium",
  ].map((key) => numberAt(dcf, key));

  if (values.some((value) => value === null)) return null;

  const [costOfCapital] = calcCostOfCapital(...(values as Parameters<typeof calcCostOfCapital>));
  return Number.isFinite(costOfCapital) ? costOfCapital : null;
}

function buildRow(
  fin: Doc,
  overview: Doc | undefined,
  dcf: Doc | undefined,
  closes: number[],
): FinancialComparisonRow {
  const rev = ttm(fin, "Revenue TTM", "Revenue Prev TTM");
  const ni = ttm(fin, "Net Income TTM", "Net Income Prev TTM");
  const ebitda = ttm(fin, "EBITDA TTM", "EBITDA Prev TTM");
  const ebit = ttm(fin, "EBIT TTM", "EBIT Prev TTM");
  const finNumber = (key: string) => numberAt(fin, key);
  const dcfNumber = (key: string) => numberAt(dcf, key);
  const price = finNumber("Price");
  const weekHigh = finNumber("52-Week High");
  const marketCap = finNumber("Market Cap");
  const ev = finNumber("Enterprise Value");
  const equity = dcfNumber("book_value_of_equity");
  const debt = dcfNumber("book_value_of_debt");
  const cash = dcfNumber("cash_and_marketable_securities");
  const capital = equity === null || debt === null || cash === null
    ? null
    : equity + debt - cash - (dcfNumber("cross_holdings_and_other_non_operating_assets") ?? 0);
  const usableCapital = nonZero(capital);
  const pe = finNumber("P/E") ?? finNumber("PE") ?? finNumber("trailingPE") ?? ratio(marketCap, ni.latest);
  const forwardPe = finNumber("Forward PE") ?? finNumber("Forward P/E") ?? finNumber("forwardPE") ?? numberAt(overview, "valuation", "forwardPe");
  const priceToSales = finNumber("Price to Sales") ?? finNumber("Price/Sales") ?? finNumber("priceToSalesTrailing12Months") ?? ratio(marketCap, rev.latest);

  return {
    Ticker: String(fin.Ticker ?? ""),
    Name: normalizeCompanyName(fin.Name),
    ttmPeriodEnd: typeof fin["TTM Period End"] === "string" ? fin["TTM Period End"] : null,
    pctOf52WeekHigh: price !== null && weekHigh !== null && weekHigh !== 0 ? (price / weekHigh) * 100 : null,
    revenue: rev.latest,
    netIncome: ni.latest,
    ebitda: ebitda.latest,
    ebit: ebit.latest,
    priceToFcf: ratio(marketCap, finNumber("Free Cash Flow TTM")),
    pe,
    forwardPe,
    priceToSales,
    netProfitMargin: ratio(ni.latest, rev.latest),
    operatingMargin: ratio(ebit.latest, rev.latest),
    ebitdaMargin: ratio(ebitda.latest, rev.latest),
    revenueGrowth: growth(rev.latest, rev.previous),
    ebitdaGrowth: growth(ebitda.latest, ebitda.previous),
    evToEbitda: ratio(ev, ebitda.latest),
    evToSales: ratio(ev, rev.latest),
    interestCoverage: ratio(ebit.latest, Math.abs(dcfNumber("interest_expense") ?? 0)),
    roic: ratio(
      ebit.latest === null ? null : ebit.latest * (1 - Math.max(0, Math.min(dcfNumber("marginal_tax_rate") ?? 0, 1))),
      usableCapital,
    ),
    wacc: wacc(dcf),
    netDebtToEbitda: debt === null || cash === null ? null : ratio(debt - cash, ebitda.latest),
    epsCurrentYear: numberAt(overview, "eps", "estimates", "currentYear", "avg"),
    epsNextYear: numberAt(overview, "eps", "estimates", "nextYear", "avg"),
    forecastRevenueNtm: forecastRevenue(dcf, rev.latest),
    forecastRevenueCagr: dcfNumber("compounded_annual_revenue_growth_rate"),
    forecastOperatingMargin: dcfNumber("target_pre_tax_operating_margin"),
    salesToCapital: ratio(rev.latest, usableCapital),
    peRange90d: historicalPeRange(closes, price, pe, 90),
    peRange1y: historicalPeRange(closes, price, pe, 365),
    capitalStructure: capitalStructure(cash, debt, equity),
  };
}

async function fetchCloses(ticker: string): Promise<number[]> {
  try {
    const response = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1y&interval=1d`,
      { cache: "no-store" },
    );
    if (!response.ok) return [];

    const data = await response.json();
    const closes: unknown[] = data?.chart?.result?.[0]?.indicators?.quote?.[0]?.close ?? [];
    return closes.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  } catch {
    return [];
  }
}

function indexByTicker(docs: Doc[]) {
  return new Map(docs.map((doc) => [String(doc.Ticker).toUpperCase(), doc]));
}

export async function GET(request: Request) {
  await dbConnect();
  const tickersParam = new URL(request.url).searchParams.get("tickers")?.trim() ?? "";
  if (!tickersParam) return Response.json([]);

  const tickers = Array.from(
    new Set(tickersParam.split(",").map((ticker) => ticker.trim().toUpperCase()).filter(Boolean)),
  ).slice(0, MAX_TICKERS);
  if (!tickers.length) return Response.json([]);

  const [finDocs, overviewDocs, dcfDocs, ...closes] = await Promise.all([
    Financials.find({ Ticker: { $in: tickers } }, { _id: 0 }).lean() as Promise<Doc[]>,
    TickerOverview.find({ Ticker: { $in: tickers } }, { _id: 0 }).lean() as Promise<Doc[]>,
    DCFInput.find({ Ticker: { $in: tickers } }, { _id: 0 }).lean() as Promise<Doc[]>,
    ...tickers.map(fetchCloses),
  ]);

  const finByTicker = indexByTicker(finDocs);
  const overviewByTicker = indexByTicker(overviewDocs);
  const dcfByTicker = indexByTicker(dcfDocs);

  const rows = tickers.flatMap((ticker, index) => {
    const fin = finByTicker.get(ticker);
    return fin ? [buildRow(fin, overviewByTicker.get(ticker), dcfByTicker.get(ticker), closes[index])] : [];
  });

  return Response.json(rows);
}
