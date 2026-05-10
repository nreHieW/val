import dbConnect from "../../../lib/dbconnect";
import DCFInput from "@/app/(models)/DcfInputs";

const SEARCH_LIMIT = 20;

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export async function GET(request: Request) {
  await dbConnect();
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("query")?.trim() ?? "";
  if (!query) {
    return Response.json([]);
  }

  const escapedQuery = escapeRegex(query);
  const tickerPrefix = new RegExp(`^${escapeRegex(query.toUpperCase())}`);
  const namePrefix = new RegExp(`^${escapedQuery}`, "i");

  const tickerMatches = await DCFInput.find(
    { Ticker: tickerPrefix },
    { _id: 0, Ticker: 1, name: 1 },
  )
    .sort({ Ticker: 1 })
    .limit(SEARCH_LIMIT)
    .lean();

  if (tickerMatches.length >= SEARCH_LIMIT) {
    return Response.json(tickerMatches);
  }

  const nameMatches = await DCFInput.find(
    { name: namePrefix, Ticker: { $nin: tickerMatches.map((item) => item.Ticker) } },
    { _id: 0, Ticker: 1, name: 1 },
  )
    .sort({ name: 1, Ticker: 1 })
    .limit(SEARCH_LIMIT - tickerMatches.length)
    .lean();

  return Response.json([...tickerMatches, ...nameMatches]);
}
