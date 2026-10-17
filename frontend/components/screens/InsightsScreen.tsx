"use client";

import Link from "next/link";
import { useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { MonthStepper } from "@/components/transactions/MonthStepper";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { useMonthSummary } from "@/lib/api/queries";
import {
  type BillAnalysis,
  type Recommendation,
  type SpendingInsights,
  useBillAnalysis,
  useRecommendations,
  useSetBudget,
  useSpendingInsights,
} from "@/lib/api/topic";
import { formatDate, formatMonth, formatPercent, plural } from "@/lib/format";
import { changeLine, formatSource, SEVERITY_COPY, STATUS_COPY } from "@/lib/insights";
import { formatRm } from "@/lib/money";
import { currentMonth, startingMonth } from "@/lib/months";

export function InsightsScreen() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Insights"
        intro="What to do next, what you owe and how your spending moved. Every figure says where it came from."
      />
      <Recommendations />
      <Bills />
      <Spending />
    </div>
  );
}

// ------------------------------------------------------------------ recommendations
export function Recommendations() {
  const recs = useRecommendations();
  return (
    <section aria-labelledby="recs-heading">
      <h2 id="recs-heading" className="mb-3 text-[15px] font-semibold text-ink">
        What to do next
      </h2>
      {recs.isPending ? (
        <Skeleton lines={4} label="Loading recommendations" />
      ) : recs.isError ? (
        <ErrorState message={recs.error.message} onRetry={() => recs.refetch()} />
      ) : recs.data.items.length === 0 ? (
        <EmptyState title="Nothing to act on right now">
          PaySense checked {plural(recs.data.checked_rules.length, "rule")} against your forecast,
          budgets, bills and spending.
        </EmptyState>
      ) : (
        <ol className="space-y-3">
          {recs.data.items.map((rec) => (
            <li key={`${rec.rule}-${rec.title}`}>
              <RecommendationCard rec={rec} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function RecommendationCard({ rec }: { rec: Recommendation }) {
  const severity = SEVERITY_COPY[rec.severity];
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-ink">{rec.title}</h3>
        <span className={`text-[11px] font-semibold uppercase tracking-wide ${severity.text}`}>
          <span aria-hidden>{severity.glyph} </span>
          {severity.label}
        </span>
      </div>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-secondary">{rec.detail}</p>
      {rec.sources.length > 0 && (
        <details className="mt-2 text-[12px]">
          <summary className="cursor-pointer text-ink-secondary">
            Where these figures come from
          </summary>
          <ul className="mt-1.5 space-y-0.5">
            {rec.sources.map((s) => (
              <li key={`${s.label}-${s.source}`} className="text-ink-secondary">
                {s.label}: <span className="font-medium text-ink">{formatSource(s)}</span>{" "}
                <span className="text-ink-muted">({s.source})</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {rec.action && (
        <div className="mt-3">
          <RecommendationAction rec={rec} />
        </div>
      )}
    </Card>
  );
}

function RecommendationAction({ rec }: { rec: Recommendation }) {
  const action = rec.action!;
  const [open, setOpen] = useState(false);
  const save = useSetBudget();
  if (action.kind === "link" && action.href) {
    return (
      <Link
        href={action.href}
        className="inline-flex h-8 items-center rounded-lg border border-line bg-surface px-3 text-xs font-semibold text-ink hover:bg-surface-2"
      >
        {action.label}
      </Link>
    );
  }
  const payload = action.payload ?? {};
  const category = String(payload.category ?? "");
  const limit = Number(payload.limit_sen ?? 0);
  return (
    <>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        {action.label}
      </Button>
      <Dialog
        open={open}
        title="Set this budget?"
        onClose={() => setOpen(false)}
        dismissible={!save.isPending}
      >
        {save.isSuccess ? (
          <Banner tone="success" title="Budget saved">
            {category}: {formatRm(limit)} a month.
          </Banner>
        ) : (
          <p className="text-[13px] text-ink-secondary">
            A {category} budget of {formatRm(limit)} a month (what you spent there the month
            before). You can change it any time on Budgets.
          </p>
        )}
        {save.isError && (
          <p role="alert" className="mt-2 text-[12px] text-danger">
            {save.error.message}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setOpen(false)}>
            {save.isSuccess ? "Close" : "Cancel"}
          </Button>
          {!save.isSuccess && (
            <Button
              variant="accent"
              disabled={save.isPending || !category || !limit}
              onClick={() => save.mutate({ category, limit_sen: limit })}
            >
              {save.isPending ? "Saving…" : "Confirm"}
            </Button>
          )}
        </div>
      </Dialog>
    </>
  );
}

// ------------------------------------------------------------------ bills
function Bills() {
  const bills = useBillAnalysis();
  return (
    <section aria-labelledby="bills-heading">
      <h2 id="bills-heading" className="mb-3 text-[15px] font-semibold text-ink">
        Bills and what is due
      </h2>
      {bills.isPending ? (
        <Skeleton lines={4} label="Loading bills" />
      ) : bills.isError ? (
        <ErrorState message={bills.error.message} onRetry={() => bills.refetch()} />
      ) : (
        <BillAnalysisView data={bills.data} />
      )}
    </section>
  );
}

export function BillAnalysisView({ data }: { data: BillAnalysis }) {
  const share = data.recurring.bills_share;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile
          label="Recurring bills a month"
          value={formatRm(data.recurring.monthly_total_sen)}
          note={plural(data.recurring.count, "confirmed bill")}
        />
        <StatTile
          label="Share of recurring income"
          value={share === null ? "—" : formatPercent(share)}
          note={share === null ? "No confirmed recurring income yet." : undefined}
        />
        <StatTile
          label={`Due in the next ${data.window_days} days`}
          value={formatRm(data.upcoming_total_sen)}
        />
      </div>
      {data.collisions.map((c) => (
        <Banner
          key={`${c.start}`}
          tone="warning"
          title={`${plural(c.items.length, "payment")} in the same week`}
        >
          {formatRm(c.total_sen)} is due between {formatDate(c.start)} and {formatDate(c.end)}:{" "}
          {c.items.map((i) => `${i.name} (${formatRm(i.amount_sen)})`).join(", ")}.
        </Banner>
      ))}
      {data.increases.map((inc) => (
        <Banner key={inc.item_id} tone="info" title={`${inc.name} went up`}>
          From {formatRm(inc.previous_sen)} ({formatDate(inc.previous_date)}) to{" "}
          {formatRm(inc.latest_sen)} ({formatDate(inc.latest_date)}).
        </Banner>
      ))}
      <Card>
        <CardTitle>The next {data.window_days} days</CardTitle>
        {data.upcoming.length === 0 ? (
          <p className="mt-2 text-[13px] text-ink-secondary">Nothing is due.</p>
        ) : (
          <ul className="mt-2 divide-y divide-line text-[13px]">
            {data.upcoming.map((d) => (
              <li
                key={`${d.kind}-${d.name}-${d.due_date}-${d.seq ?? ""}`}
                className="flex justify-between gap-3 py-2"
              >
                <span>
                  <span className="font-medium text-ink">{d.name}</span>{" "}
                  <span className="text-ink-muted">
                    {d.kind === "instalment" ? `${d.provider_label ?? "BNPL"} instalment` : "bill"}
                  </span>
                  {d.overdue && <span className="ml-1 font-semibold text-danger">overdue</span>}
                </span>
                <span className="shrink-0 tabular-nums text-ink">
                  {formatDate(d.due_date)} · {formatRm(d.amount_sen)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ spending
function Spending() {
  const summary = useMonthSummary();
  const now = currentMonth();
  const first = summary.data?.months[0]?.month ?? now;
  const [chosen, setChosen] = useState<string | null>(null);
  const month = chosen ?? (summary.data ? startingMonth(summary.data.months, now) : null);
  const insights = useSpendingInsights(month);
  return (
    <section aria-labelledby="spending-heading">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="spending-heading" className="text-[15px] font-semibold text-ink">
          How your spending moved
        </h2>
        {month && <MonthStepper month={month} min={first} max={now} onChange={setChosen} />}
      </div>
      {summary.isPending || insights.isPending ? (
        <Skeleton lines={5} label="Loading spending insights" />
      ) : insights.isError ? (
        <ErrorState message={insights.error.message} onRetry={() => insights.refetch()} />
      ) : (
        <SpendingView data={insights.data} />
      )}
    </section>
  );
}

export function SpendingView({ data }: { data: SpendingInsights }) {
  return (
    <div className="space-y-4">
      <Card>
        <p className="font-serif text-[18px] font-semibold text-ink">{data.headline}</p>
        <CardCaption>
          {data.previous_month
            ? `Compared with ${formatMonth(data.previous_month)}.`
            : "This is your first month with data, so there is nothing to compare with yet."}
        </CardCaption>
      </Card>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Income" value={formatRm(data.income_sen)} />
        <StatTile label="Spent" value={formatRm(data.spend_sen)} />
        <StatTile
          label="Kept"
          value={data.savings_rate === null ? "—" : formatPercent(Math.max(data.savings_rate, 0))}
          note={
            data.savings_rate === null
              ? "No income logged this month."
              : `${formatRm(data.left_over_sen)} left over${data.savings_sen ? `; ${formatRm(data.savings_sen)} set aside as savings` : ""}.`
          }
        />
      </div>
      {data.movers.length > 0 && (
        <Card>
          <CardTitle>Biggest changes</CardTitle>
          <ul className="mt-2 space-y-1 text-[13px]">
            {data.movers.map((m) => (
              <li key={m.category}>
                <span className="font-medium text-ink">{m.category}</span>{" "}
                <span className="text-ink-secondary">{changeLine(m)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card>
        <CardTitle>Unusual transactions</CardTitle>
        <CardCaption>
          Compared with your own earlier spending in the same category (above the median plus{" "}
          {data.mad_k} robust standard deviations).
        </CardCaption>
        {data.unusual.length === 0 ? (
          <p className="mt-2 text-[13px] text-ink-secondary">Nothing stood out.</p>
        ) : (
          <ul className="mt-2 divide-y divide-line text-[13px]">
            {data.unusual.map((u) => (
              <li key={u.transaction_id} className="flex justify-between gap-3 py-2">
                <span>
                  <span className="font-medium text-ink">{u.description ?? u.category}</span>{" "}
                  <span className="text-ink-muted">
                    {formatDate(u.date)} · usually about {formatRm(u.median_sen)}
                  </span>
                </span>
                <span className="font-semibold tabular-nums text-ink">
                  {formatRm(u.amount_sen)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {data.unusual_note && (
          <p className="mt-2 text-[12px] text-ink-muted">{data.unusual_note}</p>
        )}
      </Card>
      {data.categories.length > 0 && (
        <Card>
          <CardTitle>Every category</CardTitle>
          <table className="mt-2 w-full text-left text-[13px]">
            <caption className="sr-only">Spending by category against the month before</caption>
            <thead className="text-[11px] uppercase tracking-wide text-ink-muted">
              <tr>
                <th scope="col" className="py-1.5">
                  Category
                </th>
                <th scope="col" className="py-1.5 text-right">
                  This month
                </th>
                <th scope="col" className="py-1.5 text-right">
                  Before
                </th>
                <th scope="col" className="py-1.5 text-right">
                  Change
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.categories.map((c) => (
                <tr key={c.category}>
                  <th scope="row" className="py-1.5 font-medium text-ink">
                    {c.category}
                  </th>
                  <td className="py-1.5 text-right tabular-nums">{formatRm(c.spend_sen)}</td>
                  <td className="py-1.5 text-right tabular-nums">{formatRm(c.previous_sen)}</td>
                  <td className="py-1.5 text-right text-ink-secondary">{STATUS_COPY[c.status]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
