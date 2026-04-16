import { Roboto_Slab } from "next/font/google";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Code } from "lucide-react";

const logoFont = Roboto_Slab({ subsets: ["latin"] });

const linkClassName =
  "underline decoration-border underline-offset-4 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-sm";

export default function AboutPage() {
  return (
    <main className="pb-12 sm:pb-16">
      <article className="w-full text-xs leading-6 text-muted-foreground text-justify space-y-8">
        <section className="space-y-3">
          <h1 className={`${logoFont.className} text-2xl text-foreground`}>what is val.</h1>
          <p>
            Val is modelled after Professor Aswath Damodaran&apos;s{" "}
            <a
              href="https://www.youtube.com/watch?v=kyKfJ_7-mdg"
              target="_blank"
              rel="noopener noreferrer"
              className={linkClassName}
            >
              spreadsheet
            </a>
            . It streamlines company valuation by gathering key data automatically,
            so you can focus on what matters most: forecasting assumptions.
          </p>
        </section>

        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className={`${logoFont.className} text-2xl text-foreground`}>the model</h2>
            <HoverCard>
              <HoverCardTrigger
                className="inline-flex h-7 w-7 items-center justify-center text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-sm"
                aria-label="Open modelling code reference"
              >
                <Code className="h-4 w-4" />
              </HoverCardTrigger>
              <HoverCardContent className="max-w-64">
                <p className="text-xxs leading-5 text-muted-foreground">
                  The modelling code is{" "}
                  <a
                    href="https://gist.github.com/nreHieW/6365cb92523f0d347c1338d22f74f780"
                    target="_blank"
                    rel="noopener noreferrer"
                    className={linkClassName}
                  >
                    available here
                  </a>
                  .
                </p>
              </HoverCardContent>
            </HoverCard>
          </div>
          <p>
            Val uses a Discounted Cash Flow model that estimates expected company cash
            flows and discounts them to present value.
          </p>

          <div className="space-y-2">
            <h3 className="text-sm font-medium tracking-tight text-foreground">Cost of Capital</h3>
            <p>
              The discount rate is determined by Cost of Capital, representing the return
              required to justify the initial investment. It is a weighted average of Cost
              of Equity and Cost of Debt and decays over time as mature companies approach
              a long-run average rate.
            </p>
            <p>
              Cost of Equity combines Risk-Free Rate, Beta, and Equity Risk Premium. Val
              uses a bottom-up approach to relever Beta from Unlevered Beta, and includes
              country risk premium where relevant.
            </p>
            <p>
              Cost of Debt reflects the long-term borrowing rate, including default risk
              and interest-rate conditions. Following Professor Damodaran&apos;s approach,
              Val computes synthetic ratings using Interest Coverage Ratio (EBIT / Interest
              Expenses).
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-medium tracking-tight text-foreground">Growth</h3>
            <p>
              Val gathers consensus growth estimates from multiple sources, while still
              encouraging personal forecasts.
            </p>
            <p>
              To reduce unjustified growth assumptions, Val requires growth to be earned
              through reinvestment. Concretely, growth depends on both Reinvestment *
              Return on Invested Capital and growth from efficiency improvements.
            </p>
            <p>
              To keep terminal assumptions realistic, growth decays toward the Risk-Free
              Rate so the company does not outgrow the economy in perpetuity.
            </p>
          </div>

          <p>
            Final firm value combines the present value of projected cash flows and
            terminal value, adjusted for failure probability, debt, minority interest,
            employee options, cash, and non-operating assets.
          </p>
        </section>

        <section id="inputs_description" className="space-y-3">
          <h2 className={`${logoFont.className} text-2xl text-foreground`}>the inputs</h2>
          <ul className="space-y-2 marker:text-muted-foreground list-disc pl-4">
            <li>
              <span className="font-medium text-foreground">Revenues:</span> Current-year
              operating revenues. Adjust only when operating revenue is misclassified or a
              business segment is missing.
            </li>
            <li>
              <span className="font-medium text-foreground">
                Next Year Revenue Growth, Operating Margin, and Compounded Annual Revenue Growth:
              </span>{" "}
              The primary forecast assumptions.
            </li>
            <li>
              <span className="font-medium text-foreground">Target Pre-tax Operating Margin:</span>{" "}
              Expected efficiency level, typically anchored to industry averages.
            </li>
            <li>
              <span className="font-medium text-foreground">Year of Convergence for Margin:</span>{" "}
              Time needed to reach target operating margin.
            </li>
            <li>
              <span className="font-medium text-foreground">Discount Rate:</span> Use when
              applying an externally derived discount-rate approach.
            </li>
            <li>
              <span className="font-medium text-foreground">Years of High Growth:</span> Years
              before mature-state growth dynamics begin.
            </li>
            <li>
              <span className="font-medium text-foreground">Sales/Capital:</span> Growth
              efficiency ratio, defaulting to industry averages.
            </li>
            <li>
              <span className="font-medium text-foreground">Probability of Failure:</span>{" "}
              Default risk estimate. By default, Val derives this from synthetic rating and
              assumes 50% of book value is salvageable in failure.
            </li>
            <li>
              <span className="font-medium text-foreground">Value of Options:</span> Employee
              options to account for in final equity value.
            </li>
            <li>
              <span className="font-medium text-foreground">Adjust R&amp;D Expense:</span>{" "}
              Following Professor Damodaran, R&amp;D is capitalized as an asset rather than
              expensed. Learn more{" "}
              <a
                href="https://www.youtube.com/watch?v=Y_UpzqNk3I4"
                target="_blank"
                rel="noopener noreferrer"
                className={linkClassName}
              >
                here
              </a>
              .
            </li>
          </ul>
        </section>

        <section className="space-y-3">
          <h2 className={`${logoFont.className} text-2xl text-foreground`}>faqs</h2>
          <Accordion type="single" collapsible>
            <AccordionItem value="item-1">
              <AccordionTrigger>Why is my Value Per Share negative?</AccordionTrigger>
              <AccordionContent className="text-xs leading-6 text-muted-foreground">
                This is often due to the company&apos;s business model. For example, capital-
                heavy companies may carry high book debt from leases. One remedy is to
                manually adjust book debt assumptions, but deeper company analysis is
                still required.
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="item-2">
              <AccordionTrigger>Why is my Value Per Share so high?</AccordionTrigger>
              <AccordionContent className="text-xs leading-6 text-muted-foreground">
                High values are commonly driven by optimistic growth assumptions. Val
                aggregates consensus data by default, but you should still input and test
                your own assumptions.
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="item-3">
              <AccordionTrigger>I cannot find my company?</AccordionTrigger>
              <AccordionContent className="text-xs leading-6 text-muted-foreground">
                Val currently supports companies listed on NYSE and NASDAQ.
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </section>
      </article>
    </main>
  );
}
