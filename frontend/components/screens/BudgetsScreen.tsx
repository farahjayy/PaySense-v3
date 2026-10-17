"use client";

import { useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile } from "@/components/ui/StatTile";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { useCategories } from "@/lib/api/queries";
import {
  type BudgetStatusItem,
  type BudgetSuggestion,
  useBudgetStatus,
  useDeleteBudget,
  useSetBudget,
  useSuggestBudget,
} from "@/lib/api/topic";
import {
  barPercent,
  INCOME_BASIS_COPY,
  NOT_BUDGETABLE,
  paceLine,
  remainingLine,
  spentOfLimit,
  STATE_COPY,
} from "@/lib/budgets";
import { formatMonth, plural } from "@/lib/format";
import { formatRm } from "@/lib/money";

export function BudgetsScreen() {
  const status = useBudgetStatus();
  const month = status.data?.month;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="Budgets"
        intro={`A monthly limit for each kind of spending${month ? `: ${formatMonth(month)} so far` : ""}, counted the same way as your spending by category.`}
      />
      {status.isPending ? (
        <Skeleton lines={5} label="Loading budgets" />
      ) : status.isError ? (
        <ErrorState message={status.error.message} onRetry={() => status.refetch()} />
      ) : (
        <>
          <section aria-label="This month" className="grid gap-3 sm:grid-cols-3">
            <StatTile label="Budgeted" value={formatRm(status.data.total_limit_sen)} />
            <StatTile label="Spent in budgets" value={formatRm(status.data.total_spent_sen)} />
            <StatTile
              label="Spent elsewhere"
              value={formatRm(status.data.unbudgeted_spend_sen)}
              note="In categories with no budget, BNPL instalments included."
            />
          </section>
          {status.data.items.length === 0 ? (
            <EmptyState title="No budgets yet">
              Add one below, or let PaySense suggest a set from your income, bills and recent
              spending.
            </EmptyState>
          ) : (
            <ul className="space-y-3" aria-label="Your budgets">
              {status.data.items.map((item) => (
                <BudgetRow key={item.category} item={item} />
              ))}
            </ul>
          )}
          <AddBudget taken={status.data.items.map((i) => i.category.toLowerCase())} />
          <Suggest />
        </>
      )}
    </div>
  );
}

function BudgetRow({ item }: { item: BudgetStatusItem }) {
  const state = STATE_COPY[item.state];
  const pace = paceLine(item.projected_sen, item.projected_state);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const remove = useDeleteBudget();
  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[15px] font-semibold text-ink">{item.category}</h2>
          <p className={`text-[12px] font-semibold ${state.text}`}>
            <span aria-hidden>{state.glyph} </span>
            {state.label}
          </p>
        </div>
        <div
          role="progressbar"
          aria-label={`${item.category} spent`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(barPercent(item.percent))}
          aria-valuetext={`${spentOfLimit(item.spent_sen, item.limit_sen)}, ${state.label}`}
          className="mt-3 h-2.5 overflow-hidden rounded-full bg-line"
        >
          <div
            className={`h-full rounded-full ${state.bar}`}
            style={{ width: `${barPercent(item.percent)}%` }}
          />
        </div>
        <p className="mt-2 text-[13px] text-ink">
          {spentOfLimit(item.spent_sen, item.limit_sen)} · {remainingLine(item.remaining_sen)}
        </p>
        {pace && <p className="mt-0.5 text-[12px] text-ink-secondary">{pace}</p>}
        <div className="mt-3 flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
            Change limit
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setConfirming(true)}>
            Remove
          </Button>
        </div>
      </Card>
      <EditDialog item={item} open={editing} onClose={() => setEditing(false)} />
      <Dialog
        open={confirming}
        title={`Remove the ${item.category} budget?`}
        onClose={() => setConfirming(false)}
        dismissible={!remove.isPending}
      >
        <p className="text-[13px] text-ink-secondary">
          Your transactions stay as they are; only the limit goes.
        </p>
        {remove.isError && (
          <p role="alert" className="mt-2 text-[12px] text-danger">
            {remove.error.message}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            Keep it
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(item.category, { onSuccess: () => setConfirming(false) })}
          >
            {remove.isPending ? "Removing…" : "Remove"}
          </Button>
        </div>
      </Dialog>
    </li>
  );
}

function EditDialog({
  item,
  open,
  onClose,
}: {
  item: BudgetStatusItem;
  open: boolean;
  onClose: () => void;
}) {
  const [sen, setSen] = useState<number | null>(item.limit_sen);
  const save = useSetBudget();
  return (
    <Dialog
      open={open}
      title={`${item.category} budget`}
      onClose={onClose}
      dismissible={!save.isPending}
    >
      <MoneyInput label="Monthly limit" valueSen={sen} onChange={setSen} required />
      {save.isError && (
        <p role="alert" className="mt-2 text-[12px] text-danger">
          {save.error.message}
        </p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="accent"
          disabled={!sen || save.isPending}
          onClick={() =>
            sen && save.mutate({ category: item.category, limit_sen: sen }, { onSuccess: onClose })
          }
        >
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </Dialog>
  );
}

function AddBudget({ taken }: { taken: string[] }) {
  const categories = useCategories();
  const [category, setCategory] = useState("");
  const [sen, setSen] = useState<number | null>(null);
  const save = useSetBudget();
  const options = (categories.data?.categories ?? []).filter(
    (c) => c.assignable && !NOT_BUDGETABLE.has(c.name) && !taken.includes(c.name.toLowerCase()),
  );
  return (
    <Card>
      <CardTitle>Add a budget</CardTitle>
      <form
        className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          if (!category || !sen) return;
          save.mutate(
            { category, limit_sen: sen },
            {
              onSuccess: () => {
                setCategory("");
                setSen(null);
              },
            },
          );
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="budget-category" className="text-xs font-medium text-ink-secondary">
            Category
          </label>
          <select
            id="budget-category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-10 rounded-lg border border-field bg-surface px-3 text-[14px] text-ink"
          >
            <option value="">Choose…</option>
            {options.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <MoneyInput label="Monthly limit" valueSen={sen} onChange={setSen} />
        <Button type="submit" variant="accent" disabled={!category || !sen || save.isPending}>
          {save.isPending ? "Saving…" : "Add budget"}
        </Button>
      </form>
      {save.isError && (
        <p role="alert" className="mt-2 text-[12px] text-danger">
          {save.error.message}
        </p>
      )}
    </Card>
  );
}

function Suggest() {
  const suggest = useSuggestBudget();
  return (
    <Card>
      <CardTitle>Suggest a budget</CardTitle>
      <CardCaption>
        Plain arithmetic, no model: your income, less your bills, your BNPL instalments and a small
        buffer, split by how you spent recently. Nothing is saved until you choose a limit.
      </CardCaption>
      <div className="mt-3">
        <Button
          variant="secondary"
          disabled={suggest.isPending}
          onClick={() => suggest.mutate(undefined)}
        >
          {suggest.isPending ? "Working it out…" : "Suggest a budget"}
        </Button>
      </div>
      {suggest.isError && (
        <p role="alert" className="mt-2 text-[12px] text-danger">
          {suggest.error.message}
        </p>
      )}
      {suggest.data && <Working suggestion={suggest.data} />}
    </Card>
  );
}

function Working({ suggestion }: { suggestion: BudgetSuggestion }) {
  const save = useSetBudget();
  const [saved, setSaved] = useState<string[]>([]);
  const lines: [string, string][] = [
    [`Income (${INCOME_BASIS_COPY[suggestion.income_basis]})`, formatRm(suggestion.income_sen)],
    ["Less recurring bills", formatRm(suggestion.bills_sen)],
    ["Less BNPL instalments due", formatRm(suggestion.instalments_sen)],
    [
      `Less a buffer (${Math.round(suggestion.buffer_rate * 100)}% of income)`,
      formatRm(suggestion.buffer_sen),
    ],
    ["Left to budget", formatRm(suggestion.pool_sen)],
  ];
  return (
    <div className="mt-4 space-y-4">
      <div>
        <h3 className="text-[13px] font-semibold text-ink">
          How we got this, for {formatMonth(suggestion.month)}
        </h3>
        <dl className="mt-2 divide-y divide-line rounded-lg border border-line text-[13px]">
          {lines.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 px-3 py-2">
              <dt className="text-ink-secondary">{label}</dt>
              <dd className="font-medium tabular-nums text-ink">{value}</dd>
            </div>
          ))}
        </dl>
        {suggestion.months_used.length > 0 && (
          <p className="mt-2 text-[12px] text-ink-secondary">
            Split by your spending in {plural(suggestion.months_used.length, "month")} (
            {suggestion.months_used.map((m) => formatMonth(m)).join(", ")}), without bills and BNPL
            payments. Each limit is rounded down to RM5.
          </p>
        )}
      </div>
      {suggestion.notes.map((note) => (
        <Banner key={note} tone="info">
          {note}
        </Banner>
      ))}
      {suggestion.items.length > 0 && (
        <table className="w-full text-left text-[13px]">
          <caption className="sr-only">Suggested limits</caption>
          <thead className="text-[11px] uppercase tracking-wide text-ink-muted">
            <tr>
              <th scope="col" className="py-1.5">
                Category
              </th>
              <th scope="col" className="py-1.5 text-right">
                Recent a month
              </th>
              <th scope="col" className="py-1.5 text-right">
                Suggested
              </th>
              <th scope="col" className="py-1.5">
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {suggestion.items.map((item) => (
              <tr key={item.category}>
                <th scope="row" className="py-2 font-medium text-ink">
                  {item.category}{" "}
                  <span className="font-normal text-ink-muted">
                    ({Math.round(item.share * 100)}%)
                  </span>
                </th>
                <td className="py-2 text-right tabular-nums">
                  {formatRm(item.recent_monthly_sen)}
                </td>
                <td className="py-2 text-right font-semibold tabular-nums">
                  {formatRm(item.limit_sen)}
                </td>
                <td className="py-2 pl-3 text-right">
                  {saved.includes(item.category) ? (
                    <span className="text-[12px] font-semibold text-success">Saved</span>
                  ) : (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={save.isPending}
                      aria-label={`Use ${formatRm(item.limit_sen)} for ${item.category}`}
                      onClick={() =>
                        save.mutate(
                          { category: item.category, limit_sen: item.limit_sen },
                          { onSuccess: () => setSaved((s) => [...s, item.category]) },
                        )
                      }
                    >
                      Use this
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {save.isError && (
        <p role="alert" className="text-[12px] text-danger">
          {save.error.message}
        </p>
      )}
    </div>
  );
}
