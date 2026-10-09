import type { ReactNode } from "react";

import { ModelVersions } from "@/components/model/ModelVersions";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card>
      <section aria-labelledby={id}>
        <h2 id={id} className="font-serif text-lg font-semibold text-ink">
          {title}
        </h2>
        <div className="mt-2 space-y-3 text-[14px] leading-relaxed text-ink-secondary">
          {children}
        </div>
      </section>
    </Card>
  );
}

/**
 * Plain-language model card. It says what each tool does, how to read the result and, as
 * prominently, where it is weak. Static on purpose: nothing here is a number from a model.
 */
export function ModelScreen() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        title="About the model"
        intro="How the forecast and the BNPL risk check work, what they were built from, and where they are weak."
      />
      <ModelVersions />
      <Section id="forecast" title="Financial health forecast">
        <p>
          It looks at the weekly pattern of your spending and income, adds the bills and instalments
          you already owe, and plays your next few months forward 1,000 times with realistic ups and
          downs. The score is the share of those futures in which your running margin never goes
          below zero.
        </p>
        <p>
          It needs about four months of history (and at least 17 complete weeks). With less, it
          shows how far you are from that instead of a number it cannot stand behind.
        </p>
      </Section>
      <Section id="risk" title="BNPL risk check">
        <p>
          You describe a purchase and a provider. The check works out the instalment schedule using
          the provider&apos;s own rules, then asks how much worse your forecast becomes with that
          plan added. A trained model turns the answer into a risk level, and a short list of the
          things that pushed it up, each written from your own figures.
        </p>
        <p>
          Your repayment history (late or overdue instalments) is shown next to the result but is
          never part of the score.
        </p>
      </Section>
      <Section id="bands" title="Reading the result">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong className="text-ink">Safe</strong>: under a 10% chance of running short.
          </li>
          <li>
            <strong className="text-ink">Caution</strong>: 10% to under 30%.
          </li>
          <li>
            <strong className="text-ink">At Risk</strong>: 30% or more.
          </li>
        </ul>
        <p>
          These cut-offs were fixed before any results were seen. They are judgements, not laws: a
          Caution is a prompt to look closer, not a verdict.
        </p>
      </Section>
      <Section id="built" title="What it was built from">
        <p>
          The forecast was compared against simple alternatives (repeating last week, a moving
          average) on public spending data and on thousands of synthetic student profiles. Real
          students&apos; finances were not used to build it, and nothing you enter is used to train
          it.
        </p>
        <p>
          The synthetic students follow rules written from published research where it exists. For
          many details, such as how often a student eats out, no published figure was available and
          a reasonable value was assumed. Those assumptions are listed in the project documentation.
        </p>
      </Section>
      <Section id="limits" title="Where it is weak">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            The range around the forecast is a little too narrow: real outcomes land inside it less
            often than the stated 8 in 10.
          </li>
          <li>
            Savings you hold are not counted as money you can fall back on, so a student with
            savings but little income may look worse off than they are.
          </li>
          <li>
            Short histories give less reliable ranges. If a month is missing or your ledger is out
            of date, the page says so beside the number.
          </li>
          <li>
            Only SPayLater, TikTok PayLater and Atome follow built-in rules. For any other provider,
            you type in the dates and amounts from your own checkout and nothing is checked.
          </li>
          <li>Providers can change their terms. Check the amounts at checkout before you pay.</li>
        </ul>
        <p className="text-ink">
          This is a decision aid, not financial advice, and it cannot see anything you have not
          logged.
        </p>
      </Section>
    </div>
  );
}
