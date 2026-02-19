export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get("ticker");

  if (!ticker) {
    return Response.json({ error: "ticker is required" }, { status: 400 });
  }

  try {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(
      ticker,
    )}?range=6mo&interval=1d`;
    const response = await fetch(url, { cache: "no-store" });

    if (!response.ok) {
      return Response.json(
        { error: "failed to fetch history" },
        { status: response.status },
      );
    }

    const data = await response.json();
    const closes =
      data?.chart?.result?.[0]?.indicators?.quote?.[0]?.close ?? [];
    const history = closes.filter(
      (value: unknown): value is number =>
        typeof value === "number" && Number.isFinite(value),
    );

    return Response.json({ history });
  } catch (_error) {
    return Response.json({ error: "failed to fetch history" }, { status: 500 });
  }
}
