import TickerDisplay from "@/components/ticker-display/ticker-display";
import { Loading } from "@/components/ui/loading";
import type { Metadata, ResolvingMetadata } from "next";
import { Suspense } from "react";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export async function generateMetadata(
  { params }: Props,
  _parent: ResolvingMetadata
): Promise<Metadata> {
  const { slug } = await params;
  const ticker = slug.split("-")[0];

  return {
    title: `val. ${ticker}`,
    description: `Valuation for ${ticker}`,
  };
}

export default async function TickerDisplayPage({
  params,
  searchParams,
}: Props) {
  const [{ slug }, resolvedSearchParams] = await Promise.all([
    params,
    searchParams,
  ]);
  const ticker = slug.split("-")[0];
  const inputsParam = resolvedSearchParams.inputs;
  const inputs = Array.isArray(inputsParam) ? inputsParam[0] ?? "" : inputsParam ?? "";

  return (
    <>
      <Suspense fallback={<div className="py-8 justify-center flex">
          <Loading />
        </div>}>
        <TickerDisplay ticker={ticker} userInputs={inputs} />
      </Suspense>
    </>
  );
}
