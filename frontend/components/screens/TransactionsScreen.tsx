"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { BnplBox } from "@/components/transactions/BnplBox";
import { CategorySpending } from "@/components/transactions/CategorySpending";
import { MonthStepper } from "@/components/transactions/MonthStepper";
import { TransactionForm } from "@/components/transactions/TransactionForm";
import { TypeButtons } from "@/components/transactions/TypeButtons";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import {
  useCategorySummary,
  useCreateTransaction,
  useDeleteTransaction,
  useMonthSummary,
  usePlans,
  useTransactions,
  useUpdateTransaction,
  type Plan,
  type Transaction,
  type TransactionInput,
} from "@/lib/api/queries";
import { useAssignableCategories } from "@/lib/categories";
import { focusPageHeading } from "@/lib/focus";
import { formatDate, formatMonth, plural } from "@/lib/format";
import { formatRm } from "@/lib/money";
import { currentMonth, monthBounds, startingMonth } from "@/lib/months";

type Dialogue =
  { kind: "add" } | { kind: "edit"; txn: Transaction } | { kind: "delete"; txn: Transaction };
type Kind = Transaction["type"];

const TYPE_LABEL = { income: "Income", expense: "Spending", savings: "Savings" } as const;
const FIELD = "h-9 rounded-lg border border-field bg-surface px-2 text-[13px] text-ink";

/** Opens on the latest month that has anything logged, so the first thing seen is real data. */
export function TransactionsScreen() {
  const summary = useMonthSummary();
  if (summary.isPending) return <Skeleton lines={6} label="Loading transactions" />;
  const months = summary.data?.months;
  const now = currentMonth();
  const first = months?.length ? months.reduce((a, m) => (m.month < a ? m.month : a), now) : now;
  const latest = startingMonth(months, now);
  return (
    <Ledger
      initialMonth={latest}
      firstMonth={first < latest ? first : latest}
      lastMonth={latest > now ? latest : now}
    />
  );
}

type LedgerProps = { initialMonth: string; firstMonth: string; lastMonth: string };

function Ledger({ initialMonth, firstMonth, lastMonth }: LedgerProps) {
  const [month, setMonth] = useState(initialMonth);
  const [type, setType] = useState<Kind | undefined>(undefined);
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [dialogue, setDialogue] = useState<Dialogue | null>(null);

  const { start, end } = monthBounds(month);
  const list = useTransactions({ start, end, ...(type && { type }), ...(category && { category }) });
  const spending = useCategorySummary(month);
  const plans = usePlans();
  const categories = useAssignableCategories([
    ...(list.data ?? []).map((t) => t.category),
    ...(category ? [category] : []),
  ]);
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const remove = useDeleteTransaction();

  const planById = useMemo(
    () => new Map<string, Plan>((plans.data ?? []).map((p) => [p.id, p])),
    [plans.data],
  );
  const needle = search.trim().toLowerCase();
  const shown = useMemo(
    () =>
      (list.data ?? []).filter(
        (t) =>
          needle === "" ||
          (t.description ?? "").toLowerCase().includes(needle) ||
          t.category.toLowerCase().includes(needle),
      ),
    [list.data, needle],
  );
  const filtered = type !== undefined || category !== undefined || needle !== "";

  function close() {
    setDialogue(null);
    create.reset();
    update.reset();
    remove.reset();
  }

  function clearFilters() {
    setType(undefined);
    setCategory(undefined);
    setSearch("");
  }

  function save(input: TransactionInput) {
    if (dialogue?.kind === "edit") {
      update.mutate({ id: dialogue.txn.id, patch: input }, { onSuccess: close });
    } else {
      create.mutate(input, { onSuccess: close });
    }
  }

  const saving = create.isPending || update.isPending;
  const saveError = create.error?.message ?? update.error?.message ?? null;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Transactions"
        intro="Everything you have logged or imported, newest first, one month at a time."
        actions={
          <>
            <Link
              href="/import"
              className="inline-flex h-10 items-center rounded-lg border border-line bg-surface px-4 text-[13px] font-semibold text-ink hover:bg-surface-2"
            >
              Import
            </Link>
            <Button variant="accent" onClick={() => setDialogue({ kind: "add" })}>
              Add transaction
            </Button>
          </>
        }
      />
      <form
        aria-label="Filter transactions"
        className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-card border border-line bg-surface px-4 py-3"
        onSubmit={(event) => event.preventDefault()}
      >
        <MonthStepper month={month} min={firstMonth} max={lastMonth} onChange={setMonth} />
        <TypeButtons value={type} onChange={setType} />
        <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
          Category
          <select
            className={FIELD}
            value={category ?? ""}
            onChange={(event) => setCategory(event.target.value || undefined)}
          >
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
            {category && !categories.includes(category) && <option value={category}>{category}</option>}
          </select>
        </label>
        <label className="flex min-w-[10rem] flex-1 flex-col gap-1 text-xs font-medium text-ink-secondary">
          Search
          <input
            type="search"
            className={`${FIELD} w-full`}
            value={search}
            placeholder="e.g. grab, mamak…"
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        {filtered && (
          <Button variant="secondary" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}
      </form>

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div>
          <p role="status" className="mb-2 min-h-[1.1rem] text-[12px] text-ink-secondary">
            {list.isSuccess ? plural(shown.length, "transaction") : ""}
          </p>
          {list.isPending ? (
            <Skeleton lines={6} label="Loading transactions" />
          ) : list.isError ? (
            <ErrorState message={list.error.message} onRetry={() => list.refetch()} />
          ) : shown.length === 0 ? (
            filtered ? (
              <EmptyState
                title="Nothing matches"
                action={
                  <Button variant="secondary" onClick={clearFilters}>
                    Clear filters
                  </Button>
                }
              >
                No transaction in {formatMonth(month)} fits those filters.
              </EmptyState>
            ) : (
              <EmptyState
                title="Nothing here yet"
                action={
                  <Button onClick={() => setDialogue({ kind: "add" })}>
                    Add your first transaction
                  </Button>
                }
              >
                Nothing is logged for {formatMonth(month)}. Add a transaction, or import a
                statement to bring in what you already have.
              </EmptyState>
            )
          ) : (
            <>
              <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
                {shown.map((t) => (
                  <Row
                    key={t.id}
                    txn={t}
                    plan={t.bnpl_plan_id ? planById.get(t.bnpl_plan_id) : undefined}
                    onEdit={() => setDialogue({ kind: "edit", txn: t })}
                    onDelete={() => setDialogue({ kind: "delete", txn: t })}
                  />
                ))}
              </ul>
            </>
          )}
        </div>
        <aside className="lg:sticky lg:top-4 lg:self-start" aria-label="Spending this month">
          <CategorySpending
            month={month}
            summary={spending.data}
            isPending={spending.isPending}
            error={spending.isError ? spending.error.message : null}
            selected={category}
            onSelect={setCategory}
          />
        </aside>
      </div>

      <Dialog
        open={dialogue?.kind === "add" || dialogue?.kind === "edit"}
        title={dialogue?.kind === "edit" ? "Edit transaction" : "Add transaction"}
        onClose={close}
        dismissible={!saving}
      >
        {(dialogue?.kind === "add" || dialogue?.kind === "edit") && (
          <TransactionForm
            initial={dialogue.kind === "edit" ? dialogue.txn : undefined}
            categories={categories}
            saving={saving}
            error={saveError}
            onSubmit={save}
            onCancel={close}
          />
        )}
      </Dialog>

      <Dialog
        open={dialogue?.kind === "delete"}
        title="Delete this transaction?"
        onClose={close}
        dismissible={!remove.isPending}
      >
        {dialogue?.kind === "delete" && (
          <div className="space-y-4">
            <p className="text-[13px] text-ink-secondary">
              {dialogue.txn.description ?? dialogue.txn.category} on {formatDate(dialogue.txn.date)}
              , {formatRm(dialogue.txn.amount_sen)}. Your forecast will update without it.
            </p>
            {remove.error && (
              <Banner tone="danger" title="Not deleted">
                {remove.error.message}
              </Banner>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={close} disabled={remove.isPending}>
                Keep it
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(dialogue.txn.id, {
                    onSuccess: () => {
                      close();
                      focusPageHeading();
                    },
                  })
                }
              >
                {remove.isPending ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}

type RowProps = {
  txn: Transaction;
  plan: Plan | undefined;
  onEdit: () => void;
  onDelete: () => void;
};

function Row({ txn, plan, onEdit, onDelete }: RowProps) {
  const sign = txn.type === "income" ? "+" : "";
  const label = txn.description ?? txn.category;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
      <div className="min-w-[10rem] flex-1">
        <p className="break-words text-[14px] font-medium text-ink">{label}</p>
        <p className="text-[12px] text-ink-secondary">
          {formatDate(txn.date)} · {txn.category} · {TYPE_LABEL[txn.type]}
        </p>
      </div>
      <span
        className={`text-[14px] font-semibold tabular-nums ${txn.type === "income" ? "text-success" : "text-ink"}`}
      >
        {sign}
        {formatRm(txn.amount_sen)}
      </span>
      {txn.bnpl_plan_id ? (
        <BnplBox plan={plan} />
      ) : (
        <div className="flex w-full justify-end gap-1 sm:w-[11.5rem]">
          <Button variant="secondary" size="sm" onClick={onEdit} aria-label={`Edit ${label}`}>
            Edit
          </Button>
          <Button variant="secondary" size="sm" onClick={onDelete} aria-label={`Delete ${label}`}>
            Delete
          </Button>
        </div>
      )}
    </li>
  );
}
