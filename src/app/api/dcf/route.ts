import { DcfInput, dcf, fillNaNWithEmptyString } from "@/lib/dcf";

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as DcfInput;
    const result = dcf(payload);
    return Response.json({
      ...result,
      df: fillNaNWithEmptyString(result.df),
    });
  } catch (error) {
    return Response.json(
      { error: "Invalid DCF request payload." },
      { status: 400 },
    );
  }
}
