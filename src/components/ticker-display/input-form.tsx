"use client";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ForecastContext, UserDCFInputs } from "./types";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "../ui/input";
import { encodeInputs, formatAmount } from "./dataHelpers";
import { usePathname, useRouter } from "next/navigation";
import InfoHover from "../info-hover";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import Link from "next/link";
import { Switch } from "../ui/switch";

const userDCFInputSchema = z.object({
  revenues: z.coerce.number(),
  revenue_growth_rate_next_year: z.coerce.number(),
  operating_margin_next_year: z.coerce.number().min(0),
  compounded_annual_revenue_growth_rate: z.coerce.number(),
  target_pre_tax_operating_margin: z.coerce.number(),
  year_of_convergence_for_margin: z.coerce.number().min(0).max(10),
  discount_rate: z.coerce.number(),
  years_of_high_growth: z.coerce.number().min(0).max(10),
  sales_to_capital_ratio_early: z.coerce.number(),
  sales_to_capital_ratio_steady: z.coerce.number(),
  prob_of_failure: z.coerce.number(),
  value_of_options: z.coerce.number(),
  adjust_r_and_d: z.coerce.boolean(),
});

type UserDCFFormValues = z.infer<typeof userDCFInputSchema>;
type NumericFieldKey = Exclude<keyof UserDCFFormValues, "adjust_r_and_d">;

type FieldValue = {
  displayLabel: string;
  key: NumericFieldKey;
  tooltip: string;
  decodeFn: (value: string) => number;
};

function formatRate(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function InputForm({
  defaults,
  forecastContext,
}: {
  defaults: UserDCFInputs;
  forecastContext?: ForecastContext;
}) {
  const router = useRouter();

  let formDefaults: UserDCFInputs = {
    revenues: defaults.revenues / 1e6,
    revenue_growth_rate_next_year: defaults.revenue_growth_rate_next_year * 100,
    operating_margin_next_year: defaults.operating_margin_next_year * 100,
    compounded_annual_revenue_growth_rate:
      defaults.compounded_annual_revenue_growth_rate * 100,
    target_pre_tax_operating_margin:
      defaults.target_pre_tax_operating_margin * 100,
    year_of_convergence_for_margin: defaults.year_of_convergence_for_margin,
    discount_rate: defaults.discount_rate * 100,
    years_of_high_growth: defaults.years_of_high_growth,
    sales_to_capital_ratio_early: defaults.sales_to_capital_ratio_early,
    sales_to_capital_ratio_steady: defaults.sales_to_capital_ratio_steady,
    prob_of_failure: defaults.prob_of_failure * 100,
    value_of_options: defaults.value_of_options / 1e6,
    adjust_r_and_d: defaults.adjust_r_and_d,
  };
  formDefaults = Object.fromEntries(
    Object.entries(formDefaults).map(([key, value]) => {
      if (typeof value === "number") {
        return [key, parseFloat(value.toFixed(2))];
      }
      return [key, value];
    })
  ) as UserDCFInputs;

  const form = useForm<UserDCFFormValues>({
    resolver: zodResolver(userDCFInputSchema),
    defaultValues: formDefaults,
  });

  const consensusRevenues = forecastContext?.consensus_revenues ?? {};
  const consensusEbit = forecastContext?.consensus_ebit ?? {};
  const sortedConsensusEntries = Object.entries(consensusRevenues).sort(
    ([leftYear], [rightYear]) => Number(leftYear) - Number(rightYear),
  );
  const currentFiscalYear = forecastContext?.current_fiscal_year;
  const nextFiscalYear = forecastContext?.next_fiscal_year;
  const currentFiscalYearConsensus = currentFiscalYear
    ? consensusRevenues[currentFiscalYear]
    : undefined;
  const nextFiscalYearConsensus = nextFiscalYear
    ? consensusRevenues[nextFiscalYear]
    : undefined;
  const currentFiscalYearConsensusEbit = currentFiscalYear
    ? consensusEbit[currentFiscalYear]
    : undefined;
  const nextFiscalYearConsensusEbit = nextFiscalYear
    ? consensusEbit[nextFiscalYear]
    : undefined;
  const quartersReported = forecastContext?.quarters_reported;
  const actualYtdRevenue = forecastContext?.actual_ytd_revenue;
  const actualYtdOperatingIncome = forecastContext?.actual_ytd_operating_income;
  const nextFiscalYearWeight = forecastContext?.next_fiscal_year_weight;
  const bridgedNtmRevenue = forecastContext?.bridged_ntm_revenue;
  const bridgedNtmOperatingIncome = forecastContext?.bridged_ntm_operating_income;
  const rollingNtmRevenues = forecastContext?.rolling_ntm_revenues ?? [];
  const currentOperatingMargin =
    typeof defaults.operating_income === "number" && defaults.revenues
      ? defaults.operating_income / defaults.revenues
      : null;
  const postBridgeEntries = nextFiscalYear
    ? sortedConsensusEntries.filter(
        ([year]) => Number(year) >= Number(nextFiscalYear),
      )
    : sortedConsensusEntries;


  const essentialFields: FieldValue[] = [
    {
      displayLabel: "Revenues",
      key: "revenues",
      tooltip: "Adjust for other sources of revenue.",
      decodeFn: (value: string) => parseFloat(value) * 1e6,
    },
    {
      displayLabel: "Next Year Revenue Growth %",
      key: "revenue_growth_rate_next_year",
      tooltip: "Expected growth rate of revenue for the next year.",
      decodeFn: (value: string) => parseFloat(value) / 100,
    },
    {
      displayLabel: "Next Year Operating Margin %",
      key: "operating_margin_next_year",
      tooltip: "Expected operating margin for the next year.",
      decodeFn: (value: string) => parseFloat(value) / 100,
    },
    {
      displayLabel: "Target Pre-tax Operating Margin",
      key: "target_pre_tax_operating_margin",
      tooltip: "Target pre-tax operating margin in steady state.",
      decodeFn: (value: string) => parseFloat(value) / 100,
    },
    {
      displayLabel: "Discount Rate %",
      key: "discount_rate",
      tooltip: "Adjust if using a different cost of capital.",
      decodeFn: (value: string) => parseFloat(value) / 100,
    },
    {
      displayLabel: "Years of High Growth",
      key: "years_of_high_growth",
      tooltip: "How long before the company reaches steady state growth. (0-10)",
      decodeFn: (value: string) => parseFloat(value),
    },
  ];

  const advancedFields: FieldValue[] = [
    {
      displayLabel: "Compounded Annual Revenue Growth %",
      key: "compounded_annual_revenue_growth_rate",
      tooltip: "Expected growth rate of revenue for the next 5 years.",
      decodeFn: (value: string) => parseFloat(value) / 100,
    },
    {
      displayLabel: "Year of Convergence for Margin",
      key: "year_of_convergence_for_margin",
      tooltip: "Number of years for the margin to converge to the target. (0-10)",
      decodeFn: (value: string) => parseFloat(value),
    },
    {
      displayLabel: "Sales/Capital (early)",
      key: "sales_to_capital_ratio_early",
      tooltip:
        "Measures capital efficiency, used to calculate reinvestment required.",
      decodeFn: (value: string) => parseFloat(value),
    },
    {
      displayLabel: "Sales/Capital (steady)",
      key: "sales_to_capital_ratio_steady",
      tooltip:
        "Measures capital efficiency, used to calculate reinvestment required.",
      decodeFn: (value: string) => parseFloat(value),
    },
    {
      displayLabel: "Prob of Failure %",
      key: "prob_of_failure",
      tooltip:
        "By default, it is calculated using synthetic rating. Adjust if actual rating is known.",
      decodeFn: (value: string) => parseFloat(value) / 100,
    },
    {
      displayLabel: "Value of Options",
      key: "value_of_options",
      tooltip:
        "Value of any options eg. stock options, warrants, etc. Assumed to be 0.",
      decodeFn: (value: string) => parseFloat(value) * 1e6,
    },
  ];
  const allFields = [...essentialFields, ...advancedFields];

  function getForecastItems(key: NumericFieldKey): { label: string; value: string }[] {
    if (key === "revenue_growth_rate_next_year") {
      return [
        { label: "TTM Revenue", value: formatAmount(defaults.revenues, true) },
        currentFiscalYear &&
        typeof currentFiscalYearConsensus === "number" &&
        typeof actualYtdRevenue === "number"
          ? { label: `FY${currentFiscalYear} YTD / Consensus`, value: `${formatAmount(actualYtdRevenue, true)} / ${formatAmount(currentFiscalYearConsensus, true)}` }
          : null,
        typeof quartersReported === "number"
          ? { label: "Quarters Reported", value: `${quartersReported}` }
          : null,
        nextFiscalYear && typeof nextFiscalYearConsensus === "number"
          ? { label: `FY${nextFiscalYear} Consensus`, value: formatAmount(nextFiscalYearConsensus, true) }
          : null,
        typeof nextFiscalYearWeight === "number"
          ? { label: "Next FY Weight (NTM)", value: formatRate(nextFiscalYearWeight) }
          : null,
        typeof bridgedNtmRevenue === "number"
          ? { label: "Adjusted NTM", value: formatAmount(bridgedNtmRevenue, true) }
          : null,
        typeof forecastContext?.ms_growth_next_year === "number"
          ? { label: "Raw FY Growth", value: formatRate(forecastContext.ms_growth_next_year) }
          : null,
        { label: "Adjusted Bridge", value: formatRate(defaults.revenue_growth_rate_next_year) },
      ].filter((x): x is { label: string; value: string } => x !== null);
    }

    if (key === "compounded_annual_revenue_growth_rate") {
      const items: { label: string; value: string }[] = [];
      if (rollingNtmRevenues.length > 0) {
        const path = rollingNtmRevenues
          .slice(0, 3)
          .map((v, i) => (i === 0 ? `NTM ${formatAmount(v, true)}` : `NTM+${i} ${formatAmount(v, true)}`))
          .join(" → ");
        items.push({ label: "Rolling 12M Path", value: path });
      } else if (postBridgeEntries.length > 0) {
        const path = postBridgeEntries
          .slice(0, 3)
          .map(([year, v]) => `FY${year} ${formatAmount(v, true)}`)
          .join(" → ");
        items.push({ label: "Consensus Path", value: path });
      }
      items.push({ label: "Default CAGR", value: formatRate(defaults.compounded_annual_revenue_growth_rate) });
      return items;
    }

    if (key === "operating_margin_next_year") {
      return [
        typeof currentOperatingMargin === "number"
          ? {
              label: "TTM Margin Floor",
              value: formatRate(currentOperatingMargin),
            }
          : null,
        currentFiscalYear &&
        typeof currentFiscalYearConsensusEbit === "number" &&
        typeof actualYtdOperatingIncome === "number"
          ? {
              label: `FY${currentFiscalYear} YTD / Consensus EBIT`,
              value: `${formatAmount(actualYtdOperatingIncome, true)} / ${formatAmount(currentFiscalYearConsensusEbit, true)}`,
            }
          : null,
        nextFiscalYear && typeof nextFiscalYearConsensusEbit === "number"
          ? {
              label: `FY${nextFiscalYear} Consensus EBIT`,
              value: formatAmount(nextFiscalYearConsensusEbit, true),
            }
          : null,
        typeof nextFiscalYearWeight === "number"
          ? { label: "Next FY Weight (NTM)", value: formatRate(nextFiscalYearWeight) }
          : null,
        typeof bridgedNtmOperatingIncome === "number"
          ? {
              label: "Bridged NTM EBIT",
              value: formatAmount(bridgedNtmOperatingIncome, true),
            }
          : null,
        typeof bridgedNtmRevenue === "number"
          ? { label: "Bridged NTM Revenue", value: formatAmount(bridgedNtmRevenue, true) }
          : null,
        typeof bridgedNtmOperatingIncome === "number" &&
        typeof bridgedNtmRevenue === "number" &&
        bridgedNtmRevenue !== 0
          ? {
              label: "Bridge Formula",
              value: "NTM EBIT / NTM Revenue",
            }
          : null,
        typeof forecastContext?.ms_margin_next_year === "number"
          ? {
              label: "Raw FY Margin",
              value: formatRate(forecastContext.ms_margin_next_year),
            }
          : null,
        {
          label: "Adjusted Bridge",
          value: formatRate(defaults.operating_margin_next_year),
        },
      ].filter((x): x is { label: string; value: string } => x !== null);
    }

    return [];
  }

  function renderForecastContext(key: NumericFieldKey) {
    const items = getForecastItems(key);
    if (items.length === 0) {
      return null;
    }

    return (
      <HoverCard>
        <HoverCardTrigger asChild>
          <button
            type="button"
            className="text-[10px] leading-none text-muted-foreground/50 hover:text-muted-foreground transition-colors cursor-help w-fit"
          >
            view context
          </button>
        </HoverCardTrigger>
        <HoverCardContent align="start" className="w-72">
          <div className="space-y-1.5">
            {items.map((item) => (
              <div key={item.label} className="flex justify-between gap-3 text-[11px]">
                <span className="text-muted-foreground/60 shrink-0">{item.label}</span>
                <span className="font-mono text-right">{item.value}</span>
              </div>
            ))}
          </div>
        </HoverCardContent>
      </HoverCard>
    );
  }

  function renderInputField(item: FieldValue) {
    return (
      <FormField
        key={item.key}
        control={form.control}
        name={item.key}
        render={({ field }) => (
          <FormItem className="flex items-center justify-between gap-4 space-y-0 py-1">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5">
                <FormLabel className="text-xs leading-snug">
                  {item.displayLabel}
                </FormLabel>
                <InfoHover text={item.tooltip} />
              </div>
              {renderForecastContext(item.key)}
            </div>
            <FormControl>
              <div className="w-28 shrink-0">
                <Input
                  {...field}
                  className="h-8 text-right"
                  placeholder={formDefaults[item.key]?.toFixed(2)}
                  value={field.value}
                />
                <FormMessage className="text-xxs mt-1" />
              </div>
            </FormControl>
          </FormItem>
        )}
      />
    );
  }

  function onSubmit(values: z.infer<typeof userDCFInputSchema>, e: any) {
    e.preventDefault();
    const newValues = { ...defaults, ...values };
    const encodedValues = Object.entries(newValues).map(([key, value]) => {
      const field = allFields.find((field) => field.key === key);
      return [key, field ? field.decodeFn(String(value)) : value];
    });
    router.push(`?inputs=${encodeInputs(Object.fromEntries(encodedValues))}?`);
  }
  const baseUrl = usePathname();
  const { reset } = form;
  return (
    <>
      <Accordion
        type="single"
        collapsible
        defaultValue={"inputs"}
        className="w-full text-base"
      >
        <AccordionItem value="inputs" className="w-full">
          <AccordionTrigger>Inputs</AccordionTrigger>
          <AccordionContent>
            <div className="flex items-baseline justify-between gap-4 mb-4">
              <p className="text-xs text-muted-foreground/50">
                All values in USD Millions or Percentages
              </p>
              <a
                href="/about#inputs_description"
                className="text-xxs text-muted-foreground/40 hover:text-muted-foreground/60 transition-colors underline underline-offset-2 shrink-0"
                target="_blank"
                rel="noopener noreferrer"
              >
                Input details
              </a>
            </div>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="flex flex-col space-y-3"
                id="inputs"
              >
                {essentialFields.map((item: FieldValue) => renderInputField(item))}
                <Accordion type="single" collapsible className="w-full">
                  <AccordionItem value="advanced">
                    <AccordionTrigger className="text-sm">
                      Advanced
                    </AccordionTrigger>
                    <AccordionContent className="space-y-3 pt-2">
                      {advancedFields.map((item: FieldValue) =>
                        renderInputField(item),
                      )}
                      <FormField
                        control={form.control}
                        name="adjust_r_and_d"
                        render={({ field }) => (
                          <FormItem className="flex items-center justify-between gap-4 space-y-0 py-1">
                            <div className="flex items-center gap-1.5">
                              <FormLabel className="text-xs leading-snug">
                                Adjust R&D Expense
                              </FormLabel>
                              <InfoHover
                                text="Capitalize R and D expenses as assets. Used to determine sales/capital ratio"
                              />
                            </div>
                            <FormControl>
                              <div className="w-28 shrink-0 flex justify-end">
                                <Switch
                                  checked={field.value}
                                  onCheckedChange={field.onChange}
                                />
                              </div>
                            </FormControl>
                          </FormItem>
                        )}
                      />
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
                <div className="flex justify-end gap-3 pt-5">
                  <Button
                    onClick={() => {
                      reset(
                        Object.fromEntries(
                          Object.entries(formDefaults).map(([key, value]) => {
                            return [key, value];
                          })
                        )
                      );
                    }}
                    variant="outline"
                    size="sm"
                  >
                    <Link href={baseUrl}>Revert</Link>
                  </Button>
                  <Button type="submit" variant="outline" size="sm">
                    Submit
                  </Button>
                </div>
              </form>
            </Form>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </>
  );
}

export default InputForm;
