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
  // console.log(dcfInputs);
  if (userInputs.length != 0) {
    let decoded: UserDCFInputs = decodeInputs(userInputs);
    dcfInputs = { ...dcfInputs, ...decoded };
  }

  dcfInputs = preprocessData(dcfInputs);
  let dcfOutput = await getDCFOutput(dcfInputs);
  // console.log(dcfOutput);
  const { value_per_share, df, cost_of_capital_components, final_components } =
    dcfOutput!;
  const terminalData = df[df.length - 1];
  const incomeStatementData = createIncomeStatementData(df);
  const revenues = df.map((item: any) => formatAmount(item.revenues));
  return (
    <TickerDisplayTabs ticker={ticker}>
      <div>
        <TopCard
          ticker={ticker}
          value_per_share={value_per_share}
          name={dcfData.name}
          final_components={final_components}
          date={dcfData.extras.last_updated_financials}
        />
        <div>
          <div className="pt-7 flex items-center">
            <div className="flex-row flex">
              <p className="text-lg">10 Year Revenue Projections</p>
              <div className="justify-center items-center ml-3 mt-1">
                <InfoHover
                  text={
                    "Revenues are broken down into operating expense, reinvestment to drive future growth and taxes, to get Free Cash Flow to Firm"
                  }
                ></InfoHover>
              </div>
            </div>
          </div>
          <div>
            <StackedBarChart data={incomeStatementData} labels={revenues} />
          </div>
        </div>
        <div className="grid sm:space-x-4 space-y-4 sm:space-y-0 my-6 sm:grid-cols-2">
          <CardItem
            title="Discount Rate"
            tooltip="Cash flows are discounted at the cost of capital which is calculated using the CAPM model."
            footerChildren={
              <>
                Cost of Capital: :&nbsp;&nbsp;&nbsp;
                {formatAmount(df[0].cost_of_capital * 100)}
              </>
            }
          >
            <>
              Cost of Debt:&nbsp;&nbsp;&nbsp;
              {(cost_of_capital_components.cost_of_debt * 100).toFixed(2)}%
              <br />
              (Levered) Beta: &nbsp;&nbsp;&nbsp;
              {cost_of_capital_components.levered_beta.toFixed(2)}
              <br />
              Risk Free Rate:&nbsp;&nbsp;&nbsp;
              {(cost_of_capital_components.risk_free_rate * 100).toFixed(2)}%
              <br />
              Equity Risk Premium:&nbsp;&nbsp;&nbsp;
              {(cost_of_capital_components.equity_risk_premium * 100).toFixed(2)}
              <br />
              Cost of Equity:&nbsp;&nbsp;&nbsp;
              {(cost_of_capital_components.cost_of_equity * 100).toFixed(2)}%
            </>
          </CardItem>
          <CardItem
            title={"Terminal Value"}
            tooltip="The value of the company at the end of the forecast period in stable growth."
            footerChildren={
              <div className="">
                Terminal Value:&nbsp;&nbsp;&nbsp;
                {formatAmount(
                  terminalData.fcff /
                    (terminalData.cost_of_capital -
                      terminalData.revenue_growth_rate)
                )}
              </div>
            }
          >
            <>
              Terminal Growth Rate:&nbsp;&nbsp;&nbsp;
              {(terminalData.revenue_growth_rate * 100).toFixed(2)}%
              <br />
              Terminal Cash Flow: &nbsp;&nbsp;&nbsp;
              {formatAmount(terminalData.fcff)}
              <br />
              Terminal Discount Rate:&nbsp;&nbsp;&nbsp;
              {(terminalData.cost_of_capital * 100).toFixed(2)}%
            </>
          </CardItem>
        </div>
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
        />
      </div>
    </TickerDisplayTabs>
  );
}
