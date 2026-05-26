import dbConnect from "@/lib/dbconnect";
import SimilarCompanies from "@/app/(models)/SimilarCompanies";

function normalizeTickers(value: unknown, sourceTicker: string): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return Array.from(
    new Set(
      value
        .map((ticker) => (typeof ticker === "string" ? ticker.trim().toUpperCase() : ""))
        .filter((ticker) => ticker.length > 0 && ticker !== sourceTicker),
    ),
  );
}

export async function GET(request: Request) {
  await dbConnect();
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get("ticker")?.trim().toUpperCase() ?? "";

  if (!ticker) {
    return Response.json({ tickers: [] });
  }

  const doc = (await SimilarCompanies.findOne(
    { Ticker: ticker },
    { _id: 0, similar_tickers: 1 },
  ).lean()) as { similar_tickers?: unknown } | null;

  return Response.json({ tickers: normalizeTickers(doc?.similar_tickers, ticker) });
}
