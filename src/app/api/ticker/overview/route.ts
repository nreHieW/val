import dbConnect from "@/lib/dbconnect";
import TickerOverview from "@/app/(models)/TickerOverview";

export async function GET(request: Request) {
  await dbConnect();
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get("ticker")?.trim().toUpperCase();

  if (!ticker) {
    return Response.json({ error: "ticker is required" }, { status: 400 });
  }

  const overview = await TickerOverview.findOne(
    { Ticker: ticker },
    { _id: 0 },
  ).lean();

  return Response.json(overview ?? null);
}
