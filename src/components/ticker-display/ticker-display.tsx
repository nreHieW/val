import TopCard from "./top-card";
import StackedBarChart from "../stacked-bar-chart";
import { getDCFInputs, getDCFOutput, getTickerOverview } from "../../lib/apiHelpers";
import {
  constructModellingData,
  createIncomeStatementData,
  decodeInputs,
  formatAmount,
  preprocessData,
} from "./dataHelpers";
import CardItem from "./card-item";
import InputForm from "./input-form";
import { DcfInput, dcf, reverseDcf } from "@/lib/dcf";
import { DCFInputData, UserDCFInputs } from "./types";
import InfoHover from "../info-hover";
import OverviewTab from "./overview-tab";
import TickerDisplayTabs from "./ticker-display-tabs";

function formatNumber(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(2);
}

function formatPercent(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(2)}%`;
}

const revenueGrowthSensitivityDeltas = [-0.05, -0.025, 0, 0.025, 0.05];

export default async function TickerDisplay({
  ticker,
  userInputs,
}: {
  ticker: string;
  userInputs: string;
}) {
  const [dcfData, overview] = await Promise.all([
    getDCFInputs(ticker),
    getTickerOverview(ticker),
  ]);
  let dcfInputs: DCFInputData = constructModellingData(dcfData);
  if (userInputs.length != 0) {
    let decoded: UserDCFInputs = decodeInputs(userInputs);
    dcfInputs = { ...dcfInputs, ...decoded };
  }

  dcfInputs = preprocessData(dcfInputs);
  let dcfOutput = await getDCFOutput(dcfInputs);
  const { value_per_share, df, cost_of_capital_components, final_components } =
    dcfOutput!;
  const terminalData = df[df.length - 1];
  const terminalSpread =
    terminalData.cost_of_capital - terminalData.revenue_growth_rate;
  const terminalValue =
    [
      terminalData.fcff,
      terminalData.cost_of_capital,
      terminalData.revenue_growth_rate,
    ].some((value) => value == null || !Number.isFinite(value)) ||
    terminalSpread === 0
      ? null
      : terminalData.fcff / terminalSpread;
  const reverseDcfOutput = reverseDcf(dcfInputs as DcfInput);
  const sensitivityRows = revenueGrowthSensitivityDeltas.map((delta) => {
    const scenarioGrowth = dcfInputs.compounded_annual_revenue_growth_rate + delta;
    const scenarioOutput = dcf({
      ...(dcfInputs as DcfInput),
      compounded_annual_revenue_growth_rate: scenarioGrowth,
    });
    return {
      delta,
      growth: scenarioGrowth,
      value: scenarioOutput.value_per_share,
      change: scenarioOutput.value_per_share - value_per_share,
    };
  });
  const incomeStatementData = createIncomeStatementData(df);
  const revenues = df.map((item: any) => formatAmount(item.revenues));
  return (
    <TickerDisplayTabs
      ticker={ticker}
      overview={
        <OverviewTab
          overview={overview}
          valuePerShare={value_per_share}
          dcfInputs={dcfInputs}
          dcfRows={df}
          reverseDcf={reverseDcfOutput}
        />
      }
    >
      <div className="space-y-0">
        <TopCard
          ticker={ticker}
          value_per_share={value_per_share}
          name={dcfData.name}
          final_components={final_components}
          date={dcfData.extras.last_updated_financials}
        />

        <section className="pt-12 sm:pt-16">
          <div className="mb-5 flex items-baseline justify-between gap-4">
            <div className="flex items-center gap-2">
              <h2 className="text-sm sm:text-base font-medium tracking-tight">10 Year Revenue Projections</h2>
              <InfoHover
                text="Revenues are broken down into operating expense, reinvestment to drive future growth and taxes, to get Free Cash Flow to Firm"
              />
            </div>
            <p className="hidden text-xxs text-muted-foreground/40 sm:block shrink-0">
              Values above bars are projected revenues
            </p>
          </div>
          <StackedBarChart data={incomeStatementData} labels={revenues} />
        </section>

        <section className="pt-10 sm:pt-12">
          <div className="grid gap-5 sm:grid-cols-2 sm:gap-6">
            <CardItem
              title="Discount Rate"
              tooltip="Cash flows are discounted at the cost of capital which is calculated using the CAPM model."
              footerChildren={
                <span>
                  Cost of Capital: {formatAmount(df[0].cost_of_capital * 100)}
                </span>
              }
            >
              <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
                <dt className="text-muted-foreground">Cost of Debt</dt>
                <dd>{formatPercent(cost_of_capital_components.cost_of_debt)}</dd>
                <dt className="text-muted-foreground">(Levered) Beta</dt>
                <dd>{formatNumber(cost_of_capital_components.levered_beta)}</dd>
                <dt className="text-muted-foreground">Risk Free Rate</dt>
                <dd>{formatPercent(cost_of_capital_components.risk_free_rate)}</dd>
                <dt className="text-muted-foreground">Equity Risk Premium</dt>
                <dd>{formatNumber(cost_of_capital_components.equity_risk_premium == null ? null : cost_of_capital_components.equity_risk_premium * 100)}</dd>
                <dt className="text-muted-foreground">Cost of Equity</dt>
                <dd>{formatPercent(cost_of_capital_components.cost_of_equity)}</dd>
              </dl>
            </CardItem>
            <CardItem
              title="Terminal Value"
              tooltip="The value of the company at the end of the forecast period in stable growth."
              footerChildren={<span>Terminal Value: {formatAmount(terminalValue)}</span>}
            >
              <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
                <dt className="text-muted-foreground">Terminal Growth Rate</dt>
                <dd>{formatPercent(terminalData.revenue_growth_rate)}</dd>
                <dt className="text-muted-foreground">Terminal Cash Flow</dt>
                <dd>{formatAmount(terminalData.fcff)}</dd>
                <dt className="text-muted-foreground">Terminal Discount Rate</dt>
                <dd>{formatPercent(terminalData.cost_of_capital)}</dd>
              </dl>
            </CardItem>
          </div>
        </section>

        <section className="pt-10 sm:pt-12">
          <CardItem
            title="Revenue Growth Sensitivity"
            tooltip="Shows value per share when the compounded annual revenue growth rate changes while all other DCF assumptions stay fixed."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted-foreground">
                  <tr className="border-b border-border/50">
                    <th className="py-2 pr-3 text-left font-normal">CAGR Change</th>
                    <th className="py-2 px-3 text-right font-normal">Revenue CAGR</th>
                    <th className="py-2 px-3 text-right font-normal">Value / Share</th>
                    <th className="py-2 pl-3 text-right font-normal">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {sensitivityRows.map((row) => (
                    <tr key={row.delta} className="border-b border-border/30 last:border-0">
                      <td className="py-2 pr-3">{row.delta === 0 ? "Base" : `${row.delta > 0 ? "+" : ""}${(row.delta * 100).toFixed(1)} pp`}</td>
                      <td className="py-2 px-3 text-right">{formatPercent(row.growth)}</td>
                      <td className="py-2 px-3 text-right font-medium">{formatAmount(row.value, true)}</td>
                      <td className={"py-2 pl-3 text-right " + (row.change > 0 ? "text-signal-positive" : row.change < 0 ? "text-signal-negative" : "text-muted-foreground")}>{row.change === 0 ? "—" : formatAmount(row.change, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardItem>
        </section>

        <section className="pt-10 sm:pt-14">
          <InputForm
            defaults={{
              revenues: dcfInputs.revenues,
              revenue_growth_rate_next_year:
                dcfInputs.revenue_growth_rate_next_year,
              operating_income:
                dcfInputs.revenues * dcfInputs.operating_margin_next_year,
              operating_margin_next_year: dcfInputs.operating_margin_next_year,
              compounded_annual_revenue_growth_rate:
                dcfInputs.compounded_annual_revenue_growth_rate,
              target_pre_tax_operating_margin:
                dcfInputs.target_pre_tax_operating_margin,
              discount_rate: df[0].cost_of_capital,
              revenue_growth_rates: df.map((row: { revenue_growth_rate: number }) => row.revenue_growth_rate),
              year_of_convergence_for_margin:
                dcfInputs.year_of_convergence_for_margin,
              years_of_high_growth: dcfInputs.years_of_high_growth,
              sales_to_capital_ratio_early: dcfInputs.sales_to_capital_ratio_early,
              sales_to_capital_ratio_steady:
                dcfInputs.sales_to_capital_ratio_steady,
              prob_of_failure: dcfInputs.prob_of_failure,
              value_of_options: dcfInputs.value_of_options,
              adjust_r_and_d: dcfInputs.r_and_d_expenses.length > 0,
            }}
            forecastContext={dcfData.extras?.forecast_context}
          />
        </section>
      </div>
    </TickerDisplayTabs>
  );
}
