"use client";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import {
  useRiskSchedule,
  type PlanInput,
  type Schedule,
} from "@/lib/api/queries";
import { formatDate, formatPercent, formatPoints, plural } from "@/lib/format";

type Option = Schedule["options"][number];

type Props = {
  /** The purchase as checked: with `onUse`, the search runs on request and an option can be used. */
  request?: PlanInput;
  onUse?: (request: PlanInput) => void;
  /** A finished search to show read-only (the assistant's card). */
  result?: Schedule;
  busy?: boolean;
};

function moved(request: PlanInput, option: Option): PlanInput {
  const next: PlanInput = {
    ...request,
    purchase_date: option.purchase_date,
    num_installments: option.num_installments,
  };
  if (request.first_payment_date)
    next.first_payment_date = option.first_payment_date;
  return next;
}

/** The Second-Opinion Check's scheduler (ADR D-57): when would this purchase hurt less? */
export function SaferTiming({ request, onUse, result, busy = false }: Props) {
  const search = useRiskSchedule();
  const shown = result ?? search.data;
  const interactive = request !== undefined && onUse !== undefined;
  return (
    <Card>
      <CardTitle>When would this hurt less?</CardTitle>
      <CardCaption>
        We try the date you entered and the day after each of your next two
        income dates, with each instalment count, until one adds at most{" "}
        {formatPoints(shown?.added_max ?? 0.05).slice(1)} to your chance of
        running short and keeps it under{" "}
        {formatPercent(shown?.at_risk_edge ?? 0.3)}.
      </CardCaption>
      {interactive && !shown && (
        <Button
          className="mt-3"
          variant="secondary"
          size="sm"
          disabled={search.isPending || busy}
          onClick={() => search.mutate(request)}
        >
          {search.isPending ? "Searching…" : "Find a better time"}
        </Button>
      )}
      {search.error && (
        <Banner tone="danger" title="The search did not run" className="mt-3">
          {search.error.message}
        </Banner>
      )}
      {shown && (
        <Outcome
          schedule={shown}
          onUse={interactive ? (o) => onUse(moved(request, o)) : undefined}
          busy={busy}
        />
      )}
    </Card>
  );
}

function Outcome({
  schedule,
  onUse,
  busy,
}: {
  schedule: Schedule;
  onUse?: (option: Option) => void;
  busy: boolean;
}) {
  if (schedule.status === "locked") {
    return (
      <p className="mt-3 text-[13px] text-ink-secondary">
        The timing search needs more history, like the check itself.
      </p>
    );
  }
  return (
    <div className="mt-3 space-y-3">
      {schedule.already_at_risk && schedule.without_probability !== null ? (
        <Banner tone="warning" title="Already At Risk without this purchase">
          Your chance of running short is{" "}
          {formatPercent(schedule.without_probability)} before you buy anything,
          so no timing can fix that on its own. Paying down what you owe first
          is the safer step.
        </Banner>
      ) : (
        schedule.chosen_index === null && (
          <Banner tone="info">
            None of the {plural(schedule.options.length, "option")} we tried
            adds at most {formatPoints(schedule.added_max).slice(1)} and stays
            under {formatPercent(schedule.at_risk_edge)}. Waiting longer or a
            lower price may help.
          </Banner>
        )
      )}
      <ul
        aria-label="Options tried"
        className="divide-y divide-line rounded-lg border border-line"
      >
        {schedule.options.map((o, i) => {
          const chosen = i === schedule.chosen_index;
          return (
            <li
              key={`${o.purchase_date}-${o.num_installments}`}
              className={`flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 text-[13px] ${chosen ? "bg-success-bg" : ""}`}
            >
              <div className="min-w-0">
                <p className="font-medium text-ink">
                  {o.as_typed
                    ? "As you entered it"
                    : `Buy on ${formatDate(o.purchase_date)}`}{" "}
                  · {plural(o.num_installments, "instalment")}
                </p>
                <p className="text-[12px] text-ink-secondary">
                  Chance of running short {formatPercent(o.with_probability)} (
                  {formatPoints(o.added_probability)})
                  {o.qualifies ? " · fits" : ""}
                </p>
              </div>
              {chosen && onUse && (
                <Button
                  variant="accent"
                  size="sm"
                  disabled={busy}
                  onClick={() => onUse(o)}
                >
                  Use this
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
