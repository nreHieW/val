import TopCard from "./top-card";
import StackedBarChart from "../stacked-bar-chart";
import { getDCFInputs, getDCFOutput } from "../../lib/apiHelpers";
import {
  constructModellingData,
  createIncomeStatementData,
  decodeInputs,
  formatAmount,
  preprocessData,
} from "./dataHelpers";
import CardItem from "./card-item";
import InputForm from "./input-form";
import { DCFInputData, UserDCFInputs } from "./types";
import InfoHover from "../info-hover";
import TickerDisplayTabs from "./ticker-display-tabs";

export default async function TickerDisplay({
  ticker,
  userInputs,
}: {
  ticker: string;
  userInputs: string;
}) {
  const dcfData = await getDCFInputs(ticker);
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
  const incomeStatementData = createIncomeStatementData(df);
  const revenues = df.map((item: any) => formatAmount(item.revenues));
  return (
    <TickerDisplayTabs ticker={ticker}>
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
                <dd>{(cost_of_capital_components.cost_of_debt * 100).toFixed(2)}%</dd>
                <dt className="text-muted-foreground">(Levered) Beta</dt>
                <dd>{cost_of_capital_components.levered_beta.toFixed(2)}</dd>
                <dt className="text-muted-foreground">Risk Free Rate</dt>
                <dd>{(cost_of_capital_components.risk_free_rate * 100).toFixed(2)}%</dd>
                <dt className="text-muted-foreground">Equity Risk Premium</dt>
                <dd>{(cost_of_capital_components.equity_risk_premium * 100).toFixed(2)}</dd>
                <dt className="text-muted-foreground">Cost of Equity</dt>
                <dd>{(cost_of_capital_components.cost_of_equity * 100).toFixed(2)}%</dd>
              </dl>
            </CardItem>
            <CardItem
              title="Terminal Value"
              tooltip="The value of the company at the end of the forecast period in stable growth."
              footerChildren={
                <span>
                  Terminal Value: {formatAmount(
                    terminalData.fcff /
                      (terminalData.cost_of_capital -
                        terminalData.revenue_growth_rate)
                  )}
                </span>
              }
            >
              <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-xs">
                <dt className="text-muted-foreground">Terminal Growth Rate</dt>
                <dd>{(terminalData.revenue_growth_rate * 100).toFixed(2)}%</dd>
                <dt className="text-muted-foreground">Terminal Cash Flow</dt>
                <dd>{formatAmount(terminalData.fcff)}</dd>
                <dt className="text-muted-foreground">Terminal Discount Rate</dt>
                <dd>{(terminalData.cost_of_capital * 100).toFixed(2)}%</dd>
              </dl>
            </CardItem>
          </div>
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
