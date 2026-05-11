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
    return new Response(JSON.stringify([]));
  }

  const escapedQuery = escapeRegex(query);
  const prefixPattern = new RegExp(`^${escapedQuery}`, "i");

  const tickers = await DCFInput.aggregate([
    {
      $match: {
        $or: [{ Ticker: prefixPattern }, { name: prefixPattern }],
      },
    },
    {
      $lookup: {
        from: "ticker_overviews",
        localField: "Ticker",
        foreignField: "Ticker",
        as: "overview",
      },
    },
    {
      $addFields: {
        overviewDoc: { $arrayElemAt: ["$overview", 0] },
      },
    },
    {
      $addFields: {
        displayName: {
          $ifNull: [
            "$name",
            {
              $ifNull: [
                "$overviewDoc.profile.name",
                { $ifNull: ["$overviewDoc.profile.shortName", "$Ticker"] },
              ],
            },
          ],
        },
        matchPriority: {
          $cond: [{ $regexMatch: { input: "$Ticker", regex: prefixPattern } }, 0, 1],
        },
      },
    },
    { $sort: { matchPriority: 1, Ticker: 1, displayName: 1 } },
    { $project: { _id: 0, Ticker: 1, name: "$displayName" } },
    { $limit: SEARCH_LIMIT },
  ]);

  return new Response(JSON.stringify(tickers));
}
