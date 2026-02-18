import { describe, expect, test } from "bun:test";
import calcFixture from "./fixtures/calc_cost_of_capital.json";
import dcfFixture from "./fixtures/dcf.json";
import randdFixture from "./fixtures/r_and_d_adjustment.json";
import {
  calcCostOfCapital,
  dcf,
  DcfInput,
  fillNaNWithEmptyString,
  rAndDAdjustment,
} from "@/lib/dcf";

const ABS_TOLERANCE = 1e-9;
const REL_TOLERANCE = 1e-9;

function nearlyEqual(actual: number, expected: number): boolean {
  if (Number.isNaN(actual) && Number.isNaN(expected)) {
    return true;
  }
  if (!Number.isFinite(actual) || !Number.isFinite(expected)) {
    return actual === expected;
  }
  const diff = Math.abs(actual - expected);
  if (diff <= ABS_TOLERANCE) {
    return true;
  }
  const maxAbs = Math.max(Math.abs(actual), Math.abs(expected), 1);
  return diff / maxAbs <= REL_TOLERANCE;
}

function expectNumericClose(actual: number, expected: number, message: string) {
  expect(
    nearlyEqual(actual, expected),
    `${message}: expected ${expected}, got ${actual}`,
  ).toBe(true);
}

describe("calcCostOfCapital parity with Python fixtures", () => {
  for (const testCase of calcFixture.cases) {
    test(testCase.name, () => {
      const [costOfCapital, components] = calcCostOfCapital(
        testCase.inputs.interest_expense,
        testCase.inputs.pre_tax_cost_of_debt,
        testCase.inputs.average_maturity,
        testCase.inputs.bv_debt,
        testCase.inputs.num_shares_outstanding,
        testCase.inputs.curr_price,
        testCase.inputs.unlevered_beta,
        testCase.inputs.tax_rate,
        testCase.inputs.risk_free_rate,
        testCase.inputs.equity_risk_premium,
      );

      expectNumericClose(
        costOfCapital,
        testCase.output.cost_of_capital,
        `${testCase.name} cost_of_capital`,
      );
      expectNumericClose(
        components.cost_of_debt,
        testCase.output.components.cost_of_debt,
        `${testCase.name} cost_of_debt`,
      );
      expectNumericClose(
        components.cost_of_equity,
        testCase.output.components.cost_of_equity,
        `${testCase.name} cost_of_equity`,
      );
      expectNumericClose(
        components.levered_beta,
        testCase.output.components.levered_beta,
        `${testCase.name} levered_beta`,
      );
      expectNumericClose(
        components.risk_free_rate,
        testCase.output.components.risk_free_rate,
        `${testCase.name} risk_free_rate`,
      );
      expectNumericClose(
        components.equity_risk_premium,
        testCase.output.components.equity_risk_premium,
        `${testCase.name} equity_risk_premium`,
      );
    });
  }
});

describe("rAndDAdjustment parity with Python fixtures", () => {
  for (const testCase of randdFixture.cases) {
    test(testCase.name, () => {
      const [adjustment, unamortizedAmount] = rAndDAdjustment(testCase.expenses);
      expectNumericClose(
        adjustment,
        testCase.output.adjustment,
        `${testCase.name} adjustment`,
      );
      expectNumericClose(
        unamortizedAmount,
        testCase.output.unamortized_amount,
        `${testCase.name} unamortized_amount`,
      );
    });
  }
});

describe("dcf parity with Python fixtures", () => {
  for (const testCase of dcfFixture.cases) {
    test(testCase.name, () => {
      const output = dcf(testCase.inputs as DcfInput);
      const serializedDf = fillNaNWithEmptyString(output.df);
      const expectedOutput = testCase.output;

      expectNumericClose(
        output.value_per_share,
        expectedOutput.value_per_share,
        `${testCase.name} value_per_share`,
      );

      expectNumericClose(
        output.cost_of_capital_components.cost_of_debt,
        expectedOutput.cost_of_capital_components.cost_of_debt,
        `${testCase.name} cost_of_debt`,
      );
      expectNumericClose(
        output.cost_of_capital_components.cost_of_equity,
        expectedOutput.cost_of_capital_components.cost_of_equity,
        `${testCase.name} cost_of_equity`,
      );
      expectNumericClose(
        output.cost_of_capital_components.levered_beta,
        expectedOutput.cost_of_capital_components.levered_beta,
        `${testCase.name} levered_beta`,
      );
      expectNumericClose(
        output.final_components.present_value_of_cash_flows,
        expectedOutput.final_components.present_value_of_cash_flows,
        `${testCase.name} present_value_of_cash_flows`,
      );

      expect(serializedDf.length).toBe(expectedOutput.df.length);
      for (let i = 0; i < serializedDf.length; i += 1) {
        const actualRow = serializedDf[i];
        const expectedRow = expectedOutput.df[i];
        expect(Object.keys(actualRow).sort()).toEqual(
          Object.keys(expectedRow).sort(),
        );

        for (const key of Object.keys(expectedRow)) {
          const actual = actualRow[key];
          const expected = expectedRow[key as keyof typeof expectedRow];
          if (typeof expected === "number") {
            expectNumericClose(
              actual as number,
              expected,
              `${testCase.name} df[${i}].${key}`,
            );
          } else {
            expect(actual).toBe(expected);
          }
        }
      }
    });
  }
});
