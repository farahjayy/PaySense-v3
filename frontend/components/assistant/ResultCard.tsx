"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { BillsDue } from "@/components/forecast/BillsDue";
import { PlanPreviewPanel } from "@/components/plans/PlanPreviewPanel";
import { RiskResult } from "@/components/risk/RiskResult";
import { SaferTiming } from "@/components/risk/SaferTiming";
import { BandBadge } from "@/components/ui/BandBadge";
import { LockedState } from "@/components/ui/States";
import type { components } from "@/lib/api/schema";
import { formatSource, type ChatCard } from "@/lib/assistant";
import { formatDate, formatMonth, formatPercent } from "@/lib/format";
import { formatRm } from "@/lib/money";

type CardOf<K extends ChatCard["kind"]> = Extract<ChatCard, { kind: K }>;

/** At most this many rows of a list are shown in a card; the screen has the rest. */
const ROWS = 6;

function Section({
  title,
  children,
  more,
}: {
  title: string;
  children: ReactNode;
  more?: ReactNode;
}) {
  return (
    <section
      className="rounded-card border border-line bg-surface p-3.5"
      aria-label={title}
    >
      <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
      <div className="mt-2 space-y-2 text-[13px] text-ink">{children}</div>
      {more && <div className="mt-2 text-[12px]">{more}</div>}
    </section>
  );
}

function ScreenLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="font-medium text-accent underline-offset-2 hover:underline"
    >
      {children}
    </Link>
  );
}

function Rows({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="divide-y divide-line">
      {items.map(([label, value], i) => (
        <div
          key={i}
          className="flex items-baseline justify-between gap-3 py-1.5"
        >
          <dt className="min-w-0 truncate text-ink-secondary">{label}</dt>
          <dd className="shrink-0 tabular-nums font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Bar({
  label,
  percent,
  state,
}: {
  label: string;
  percent: number;
  state: string;
}) {
  const shown = Math.min(Math.round(percent * 100), 100);
  const tone =
    state === "over"
      ? "bg-danger"
      : state === "near"
        ? "bg-warning"
        : "bg-success";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={shown}
      aria-valuetext={`${Math.round(percent * 100)}% used`}
      className="h-2 overflow-hidden rounded-full bg-line"
    >
      <div
        className={`h-full rounded-full ${tone}`}
        style={{ width: `${shown}%` }}
      />
    </div>
  );
}

const STATE_WORD = {
  ok: "On track",
  near: "Close to the limit",
  over: "Over the limit",
} as const;

function ForecastCardView({ data }: { data: CardOf<"forecast">["data"] }) {
  if (
    data.status !== "ok" ||
    !data.band ||
    !data.simulation ||
    data.health_score === null
  ) {
    return (
      <LockedState
        reason={data.lock_reason}
        monthsOfHistory={data.months_of_history}
      />
    );
  }
  return (
    <Section
      title="Your three-month forecast"
      more={<ScreenLink href="/">See the chart</ScreenLink>}
    >
      <BandBadge band={data.band} />
      <p>
        Health score {data.health_score} out of 100. In{" "}
        {formatPercent(data.simulation.p_shortfall)} of the simulated futures
        your running margin dips below zero.
      </p>
    </Section>
  );
}

function BillAnalysisView({ data }: { data: CardOf<"bill_analysis">["data"] }) {
  return (
    <Section
      title="Bills and what is due"
      more={<ScreenLink href="/plans">See your plans</ScreenLink>}
    >
      <Rows
        items={[
          [
            "Recurring bills a month",
            formatRm(data.recurring.monthly_total_sen),
          ],
          [
            `Due in the next ${data.window_days} days`,
            formatRm(data.upcoming_total_sen),
          ],
        ]}
      />
      {data.collisions.map((c) => (
        <p key={c.start} className="rounded-lg bg-warning-bg px-2.5 py-2">
          <span className="font-semibold">Same week:</span>{" "}
          {formatRm(c.total_sen)} between {formatDate(c.start)} and{" "}
          {formatDate(c.end)} ({c.items.map((i) => i.name).join(", ")})
        </p>
      ))}
      {data.increases.map((inc) => (
        <p key={inc.item_id}>
          {inc.name} went up from {formatRm(inc.previous_sen)} to{" "}
          {formatRm(inc.latest_sen)}.
        </p>
      ))}
      <ul className="space-y-1">
        {data.upcoming.slice(0, ROWS).map((d, i) => (
          <li
            key={`${d.name}-${d.due_date}-${i}`}
            className="flex justify-between gap-3"
          >
            <span className="min-w-0 truncate">
              {formatDate(d.due_date)} · {d.name}
              {d.overdue && (
                <span className="font-medium text-danger"> (overdue)</span>
              )}
            </span>
            <span className="tabular-nums">{formatRm(d.amount_sen)}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function InsightsView({ data }: { data: CardOf<"spending_insights">["data"] }) {
  return (
    <Section title={`How ${formatMonth(data.month)} went`}>
      <p className="font-medium">{data.headline}</p>
      <Rows
        items={[
          ["Income", formatRm(data.income_sen)],
          ["Spent", formatRm(data.spend_sen)],
          ["Left over", formatRm(data.left_over_sen)],
          ...(data.savings_rate === null
            ? []
            : ([
                [
                  "Kept of your income",
                  formatPercent(Math.max(data.savings_rate, 0)),
                ],
              ] as [string, string][])),
        ]}
      />
      {data.movers.length > 0 && (
        <ul className="space-y-1">
          {data.movers.map((m) => (
            <li key={m.category}>
              {m.category}: {formatRm(m.spend_sen)} (
              {m.change_sen >= 0 ? "up" : "down"}{" "}
              {formatRm(Math.abs(m.change_sen))})
            </li>
          ))}
        </ul>
      )}
      {data.unusual.map((u) => (
        <p
          key={u.transaction_id}
          className="rounded-lg bg-warning-bg px-2.5 py-2"
        >
          Unusual: {formatRm(u.amount_sen)} on {u.category} on{" "}
          {formatDate(u.date)} (you usually spend about {formatRm(u.median_sen)}
          )
        </p>
      ))}
      {data.unusual_note && (
        <p className="text-[12px] text-ink-secondary">{data.unusual_note}</p>
      )}
    </Section>
  );
}

function BudgetStatusView({ data }: { data: CardOf<"budget_status">["data"] }) {
  if (data.items.length === 0) {
    return (
      <Section title={`Budgets for ${formatMonth(data.month)}`}>
        <p className="text-ink-secondary">
          No budgets yet. Ask me to suggest some.
        </p>
      </Section>
    );
  }
  return (
    <Section title={`Budgets for ${formatMonth(data.month)}`}>
      {data.items.map((item) => (
        <div key={item.category} className="space-y-1">
          <div className="flex justify-between gap-3">
            <span className="font-medium">{item.category}</span>
            <span className="tabular-nums">
              {formatRm(item.spent_sen)} of {formatRm(item.limit_sen)}
            </span>
          </div>
          <Bar
            label={`${item.category} budget`}
            percent={item.percent}
            state={item.state}
          />
          <p className="text-[12px] text-ink-secondary">
            {STATE_WORD[item.state]}
            {item.projected_sen !== null &&
              ` · at this pace about ${formatRm(item.projected_sen)} by the month end`}
          </p>
        </div>
      ))}
    </Section>
  );
}

function SuggestionView({
  data,
}: {
  data: CardOf<"budget_suggestion">["data"];
}) {
  return (
    <Section title={`Suggested budgets for ${formatMonth(data.month)}`}>
      <p className="text-[12px] text-ink-secondary">How we got this:</p>
      <Rows
        items={[
          [
            data.income_basis === "average" ? "Average income" : "Income",
            formatRm(data.income_sen),
          ],
          ["Less bills", formatRm(data.bills_sen)],
          ["Less instalments", formatRm(data.instalments_sen)],
          [
            `Less a ${formatPercent(data.buffer_rate)} buffer`,
            formatRm(data.buffer_sen),
          ],
          ["Left to budget", formatRm(data.pool_sen)],
        ]}
      />
      {data.items.length > 0 && (
        <Rows
          items={data.items.map((i) => [i.category, formatRm(i.limit_sen)])}
        />
      )}
      {data.notes.map((n) => (
        <p key={n} className="text-[12px] text-ink-secondary">
          {n}
        </p>
      ))}
    </Section>
  );
}

function RecommendationsView({
  card,
}: {
  card: components["schemas"]["RecommendationsCard"];
}) {
  const alerts = card.kind === "alerts";
  if (card.data.items.length === 0) {
    return (
      <Section title={card.title}>
        <p className="text-ink-secondary">
          {alerts
            ? "Nothing needs your attention right now."
            : "No recommendations right now."}
        </p>
      </Section>
    );
  }
  return (
    <Section title={card.title}>
      <ol className="space-y-2.5">
        {card.data.items.map((r) => (
          <li
            key={`${r.rule}-${r.title}`}
            className={`rounded-lg border px-2.5 py-2 ${
              r.severity === "high"
                ? "border-danger/30 bg-danger-bg"
                : "border-line bg-surface-2"
            }`}
          >
            <p className="font-semibold">{r.title}</p>
            <p className="mt-0.5 text-ink-secondary">{r.detail}</p>
            {r.sources.length > 0 && (
              <p className="mt-1 text-[11px] text-ink-muted">
                From:{" "}
                {r.sources
                  .map((s) => `${s.label} ${formatSource(s)}`)
                  .join(" · ")}
              </p>
            )}
            {r.action?.kind === "link" && r.action.href && (
              <p className="mt-1">
                <ScreenLink href={r.action.href}>{r.action.label}</ScreenLink>
              </p>
            )}
          </li>
        ))}
      </ol>
    </Section>
  );
}

function PastePreviewView({ data }: { data: CardOf<"paste_preview">["data"] }) {
  return (
    <Section title="Transactions from your paste">
      <ul className="space-y-1">
        {data.rows.map((r, i) => (
          <li key={i} className="flex justify-between gap-3">
            <span className="min-w-0 truncate">
              {formatDate(r.date)} · {r.description ?? r.category}
              {r.duplicate && (
                <span className="font-medium text-warning">
                  {" "}
                  (already in your ledger)
                </span>
              )}
            </span>
            <span className="tabular-nums">
              {r.type === "income" ? "+" : "-"}
              {formatRm(r.amount_sen)}
            </span>
          </li>
        ))}
      </ul>
      {data.rejected.map((r) => (
        <p key={r.index} className="text-[12px] text-danger">
          Left out: {r.reason}
        </p>
      ))}
    </Section>
  );
}

/** One tool result, drawn with the app's own components where they exist. */
export function ResultCard({ card }: { card: ChatCard }) {
  switch (card.kind) {
    case "risk":
      return <RiskResult check={card.data} />;
    case "schedule":
      return <SaferTiming result={card.data} />;
    case "forecast":
      return <ForecastCardView data={card.data} />;
    case "plan_preview":
      return <PlanPreviewPanel preview={card.data} />;
    case "bills":
      return (
        <Section title={card.title}>
          <BillsDue bills={card.data} />
        </Section>
      );
    case "bill_analysis":
      return <BillAnalysisView data={card.data} />;
    case "spending_insights":
      return <InsightsView data={card.data} />;
    case "budget_status":
      return <BudgetStatusView data={card.data} />;
    case "budget_suggestion":
      return <SuggestionView data={card.data} />;
    case "recommendations":
    case "alerts":
      return <RecommendationsView card={card} />;
    case "paste_preview":
      return <PastePreviewView data={card.data} />;
    case "budgets":
      return (
        <Section
          title={card.title}
          more={<ScreenLink href="/budgets">Manage budgets</ScreenLink>}
        >
          {card.data.budgets.length === 0 ? (
            <p className="text-ink-secondary">No budgets yet.</p>
          ) : (
            <Rows
              items={card.data.budgets.map((b) => [
                b.category,
                formatRm(b.limit_sen),
              ])}
            />
          )}
        </Section>
      );
    case "month_summary":
      return (
        <Section title={card.title}>
          <Rows
            items={card.data.months
              .slice(-ROWS)
              .map((m) => [
                formatMonth(m.month),
                `${formatRm(m.income_sen)} in · ${formatRm(m.spend_sen)} out`,
              ])}
          />
        </Section>
      );
    case "category_spending":
      return (
        <Section title={card.title}>
          <Rows
            items={card.data.categories
              .slice(0, ROWS)
              .map((c) => [c.category, formatRm(c.spend_sen)])}
          />
        </Section>
      );
    case "transactions":
      return (
        <Section
          title={card.title}
          more={<ScreenLink href="/transactions">All transactions</ScreenLink>}
        >
          <Rows
            items={card.data.transactions.map((t) => [
              `${formatDate(t.date)} · ${t.description ?? t.category}`,
              `${t.type === "income" ? "+" : "-"}${formatRm(t.amount_sen)}`,
            ])}
          />
        </Section>
      );
    case "plans":
      return (
        <Section
          title={card.title}
          more={<ScreenLink href="/plans">See your plans</ScreenLink>}
        >
          {card.data.plans.length === 0 ? (
            <p className="text-ink-secondary">No BNPL plans yet.</p>
          ) : (
            <Rows
              items={card.data.plans.map((p) => [
                `${p.item_name} · ${p.provider_label}`,
                `${p.remaining_count} left of ${formatRm(p.installment_amount_sen)}`,
              ])}
            />
          )}
        </Section>
      );
    case "providers":
      return (
        <Section title={card.title}>
          <Rows
            items={card.data.limits.map((l) => [
              card.data.providers.find((p) => p.key === l.provider)?.label ??
                l.provider,
              l.limit_sen === null
                ? "No limit recorded"
                : `${formatRm(l.used_sen)} of ${formatRm(l.limit_sen)} used`,
            ])}
          />
        </Section>
      );
  }
}
