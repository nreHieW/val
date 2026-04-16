import { getPriceHistory } from "@/lib/apiHelpers";
import LineAreaChart from "../line-area-chart";
import { formatAmount } from "./dataHelpers";

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
  let value = 0;
  if (value_per_share) {
    value = calculateValue(value_per_share, currentPrice);
  }
  return (
    <div className="grid sm:grid-cols-[1fr_auto] gap-6 sm:gap-12">
      <div className="flex flex-col min-w-0">
        <div>
          <h1 className="text-base sm:text-xl font-medium tracking-tight">
            {name}
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">{ticker}</p>
        </div>
        <div className="mt-4">
          <LineAreaChart
            priceHistory={priceHistory}
            good={currentPrice > startPrice}
            title={"6M Performance"}
          />
        </div>
        <p className="text-xxs text-muted-foreground/40 mt-3 italic">
          Financials from: {date}
        </p>
      </div>

      <div className="flex flex-col sm:w-64">
        <p className="text-xxs text-muted-foreground/60 uppercase tracking-wider">Value Per Share</p>
        <p className="text-2xl sm:text-3xl font-medium tracking-tight mt-1">
          ${value_per_share.toFixed(2)}
        </p>

        <p className="text-xs leading-relaxed mt-4 text-muted-foreground">
          {value < 0 ? (
            <span className="text-signal-negative">
              Negative value — review the business model assumptions.
            </span>
          ) : (
            <span>
              Market price ${currentPrice.toFixed(2)} is{" "}
              <span className={`font-medium ${value > 100 ? "text-signal-negative" : "text-signal-positive"}`}>
                {value.toFixed(0)}%
              </span>{" "}
              of {ticker}&apos;s intrinsic value.
            </span>
          )}
        </p>

        <div className="mt-auto pt-5 border-t border-border/50">
          <ul className="space-y-1.5 text-xxs text-muted-foreground/50">
            <li className="flex justify-between gap-3">
              <span>PV of Cash Flows</span>
              <span className="tabular-nums">{formatAmount(final_components.present_value_of_cash_flows, true)}</span>
            </li>
            <li className="flex justify-between gap-3">
              <span>Book Value of Debt</span>
              <span className="tabular-nums">{formatAmount(final_components.book_value_of_debt, true)}</span>
            </li>
            <li className="flex justify-between gap-3">
              <span>Cash Equivalents</span>
              <span className="tabular-nums">{formatAmount(final_components.cash_and_marketable_securities, true)}</span>
            </li>
            <li className="flex justify-between gap-3">
              <span>Non-Operating Assets</span>
              <span className="tabular-nums">{formatAmount(final_components.cross_holdings_and_other_non_operating_assets, true)}</span>
            </li>
            <li className="flex justify-between gap-3">
              <span>Minority Interest</span>
              <span className="tabular-nums">{formatAmount(final_components.minority_interest, true)}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
