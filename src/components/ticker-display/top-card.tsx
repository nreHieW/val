import { getPriceHistory } from "@/lib/apiHelpers";
import LineAreaChart from "../line-area-chart";
import { formatAmount } from "./dataHelpers";
import { Card, CardContent } from "../ui/card";

function calculateValue(value: number, currPrice: number): number {
  return (currPrice / value) * 100;
}

export default async function TopCard({
  ticker,
  name,
  value_per_share,
  final_components,
  date,
}: {
  ticker: string;
  name: string;
  value_per_share: number;
  final_components: {
    present_value_of_cash_flows: number;
    book_value_of_debt: number;
    cash_and_marketable_securities: number;
    cross_holdings_and_other_non_operating_assets: number;
    minority_interest: number;
  };
  date: string;
}) {
  let priceHistory = await getPriceHistory(ticker);
  if (!priceHistory || priceHistory.length < 2) {
    priceHistory = [0, 0];
  }
  const currentPrice = priceHistory[priceHistory.length - 1];
  const startPrice = priceHistory[0];
  // console.log(priceHistory);
  let value = 0;
  if (value_per_share) {
    value = calculateValue(value_per_share, currentPrice);
  }
  return (
    <div className="grid sm:grid-cols-2 w-full">
      <div className="w-full h-full flex-1">
        <h1 className="text-base underline-offset-4 underline sm:text-xl">
          {name}
        </h1>
        <p className="text-xs pt-1">Ticker: {ticker}</p>
        <LineAreaChart
          priceHistory={priceHistory}
          good={currentPrice > startPrice}
          title={"6M Performance"}
        />
        <p className="text-xxs pt-4 italic" style={{ opacity: "50%" }}>
          Financials from: {date}
        </p>
      </div>
      <div className="w-full pl-5 h-full flex flex-col">
        <div className="flex flex-col h-full mt-6">
          <div className="text-sm">Value Per Share:</div>
          <div className="self-end mr-2 text-2xl">
            ${value_per_share.toFixed(2)}
          </div>
        </div>
        <div className="h-full">
          <p>
            This suggests{" "}
            {value < 0 ? (
              <span style={{ color: "rgb(218, 65, 103)" }}>
                a deeper analysis of the business model is required.
              </span>
            ) : value > 100 ? (
              <span>
                the current market price of ${currentPrice.toFixed(2)} is{" "}
                <span style={{ color: "rgb(218, 65, 103)" }}>
                  {value.toFixed(2)}% of {ticker}&apos;s intrinsic value.
                </span>
              </span>
            ) : (
              <span>
                the current market price of ${currentPrice.toFixed(2)} is{" "}
                <span style={{ color: "rgb(0, 196, 154)" }}>
                  {value.toFixed(2)}% of {ticker}&apos;s intrinsic value.
                </span>
              </span>
            )}
          </p>
          <br />

          <br />

          <Card
            className="bg-slate-50 dark:bg-zinc-950 pt-4 text-xxs"
            style={{ opacity: "50%" }}
          >
            <CardContent className="px-4 mt-0 py-4 pt-0">
              <ul className="">
                <li>
                  Present Value of All Cash Flows:{" "}
                  {formatAmount(
                    final_components.present_value_of_cash_flows,
                    true
                  )}
                </li>
                <li>
                  Book Value of Debt:{" "}
                  {formatAmount(final_components.book_value_of_debt, true)}
                </li>
                <li>
                  Cash Equivalents :{" "}
                  {formatAmount(
                    final_components.cash_and_marketable_securities,
                    true
                  )}
                </li>
                <li>
                  Non-Operating Assets:{" "}
                  {formatAmount(
                    final_components.cross_holdings_and_other_non_operating_assets,
                    true
                  )}
                </li>
                <li>
                  Minority Interest:{" "}
                  {formatAmount(final_components.minority_interest, true)}
                </li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
