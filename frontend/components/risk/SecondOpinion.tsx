import Link from "next/link";

import { Banner } from "@/components/ui/Banner";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import type { RiskCheck } from "@/lib/api/queries";
import { formatMonth, formatPercent, formatPoints, plural } from "@/lib/format";
import { formatRm } from "@/lib/money";

type Opinion = NonNullable<RiskCheck["second_opinion"]>;

function Stat({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-center">
      <p className="text-[12px] text-ink-secondary">{label}</p>
      <p
        className={`mt-0.5 tabular-nums text-ink ${strong ? "text-xl font-bold" : "text-lg font-semibold"}`}
      >
        {value}
      </p>
    </div>
  );
}

/**
 * The Second-Opinion Check (ADR D-57): what this one purchase adds to the simulated chance of
 * running short, every unpaid instalment across providers stacked by month, and the exposure
 * before and after. Every figure comes from the server; nothing is computed here.
 */
export function SecondOpinion({ opinion }: { opinion: Opinion }) {
  const { exposure } = opinion;
  // a month with nothing owed and no confirmed income adds nothing to read
  const months = opinion.stack.filter(
    (m) => m.total_sen > 0 || m.known_income_sen > 0,
  );
  const hidden = opinion.stack.length - months.length;
  return (
    <section aria-labelledby="second-opinion-title" className="space-y-4">
      <Card>
        <h2
          id="second-opinion-title"
          className="text-sm font-semibold text-ink"
        >
          What this purchase adds
        </h2>
        <CardCaption>
          From one simulation of your coming months, run without and with this
          purchase. A lender looks at one purchase; this adds up everything you
          already owe.
        </CardCaption>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <Stat
            label="Without it"
            value={formatPercent(opinion.without_probability)}
          />
          <Stat
            label="With it"
            value={formatPercent(opinion.with_probability)}
          />
          <Stat
            label="Adds"
            value={formatPoints(opinion.added_probability)}
            strong
          />
        </div>
        <p className="mt-2 text-[12px] text-ink-muted">
          The chance of running short: how often your running margin dips below
          zero across the simulated futures.
        </p>
        {opinion.already_at_risk && (
          <Banner
            tone="warning"
            title="You are already At Risk without this purchase"
            className="mt-3"
          >
            Your chance of running short is{" "}
            {formatPercent(opinion.without_probability)} before you buy
            anything, so the purchase is not the only thing to look at.
          </Banner>
        )}
      </Card>
      <Card>
        <CardTitle>Everything you owe, month by month</CardTitle>
        <CardCaption>
          Every unpaid instalment across your providers, with this purchase
          added. Anything overdue counts in this month.
          {hidden > 0 &&
            ` ${plural(hidden, "month")} with nothing due and no confirmed income ${hidden === 1 ? "is" : "are"} left out.`}
        </CardCaption>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left text-[13px]">
            <caption className="sr-only">What you owe each month</caption>
            <thead className="text-[12px] text-ink-secondary">
              <tr className="border-b border-line">
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Month
                </th>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Already owed
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  This purchase
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Total
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  Confirmed income
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {months.map((m) => (
                <tr key={m.month}>
                  <th scope="row" className="py-2 pr-3 font-medium text-ink">
                    {formatMonth(m.month)}
                  </th>
                  <td className="py-2 pr-3 text-ink-secondary">
                    {m.by_provider.length === 0
                      ? "Nothing"
                      : m.by_provider.map((p) => (
                          <span
                            key={p.provider_label}
                            className="block tabular-nums"
                          >
                            {p.provider_label} {formatRm(p.amount_sen)}
                          </span>
                        ))}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {m.new_plan_sen > 0 ? formatRm(m.new_plan_sen) : "–"}
                  </td>
                  <td className="py-2 pr-3 text-right font-semibold tabular-nums">
                    {formatRm(m.total_sen)}
                  </td>
                  <td className="py-2 text-right tabular-nums text-ink-secondary">
                    {m.known_income_sen > 0
                      ? formatRm(m.known_income_sen)
                      : "None confirmed"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <CardTitle>Your BNPL exposure</CardTitle>
        <div className="mt-2 space-y-1.5 text-[14px] leading-relaxed text-ink">
          <p>
            Unpaid across all providers: {formatRm(exposure.unpaid_before_sen)}{" "}
            to {formatRm(exposure.unpaid_after_sen)} with this purchase.
          </p>
          <p>
            {plural(exposure.providers_before.length, "provider")} to{" "}
            {exposure.providers_after.length},{" "}
            {plural(exposure.plans_before, "plan")} to {exposure.plans_after}.
          </p>
          {exposure.recorded_limits_sen !== null ? (
            <p>
              Your recorded limits add up to{" "}
              {formatRm(exposure.recorded_limits_sen)}. That is{" "}
              {exposure.reaches_bnm_line ? "at or above" : "below"}{" "}
              {formatRm(exposure.bnm_line_sen)}, the level at which Bank Negara
              Malaysia asks banks for a full affordability assessment.
            </p>
          ) : (
            <p className="text-ink-secondary">
              Record your provider limits on the{" "}
              <Link
                href="/plans"
                className="font-medium text-accent hover:underline"
              >
                Plans page
              </Link>{" "}
              to see them added up against the {formatRm(exposure.bnm_line_sen)}{" "}
              level Bank Negara Malaysia uses.
            </p>
          )}
          <p className="text-[12px] text-ink-muted">
            Shown as information about your own limits, not a judgement on any
            provider.
          </p>
        </div>
      </Card>
    </section>
  );
}
