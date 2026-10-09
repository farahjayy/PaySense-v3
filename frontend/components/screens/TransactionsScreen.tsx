"use client";

import Link from "next/link";
import { useState } from "react";

import { TransactionForm } from "@/components/transactions/TransactionForm";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import {
  useCreateTransaction,
  useDeleteTransaction,
  useTransactions,
  useUpdateTransaction,
  type Transaction,
  type TransactionFilters,
  type TransactionInput,
} from "@/lib/api/queries";
import { formatDate, plural } from "@/lib/format";
import { CATEGORIES } from "@/lib/import";
import { formatRm } from "@/lib/money";

type Dialogue =
  { kind: "add" } | { kind: "edit"; txn: Transaction } | { kind: "delete"; txn: Transaction };

const TYPE_LABEL = { income: "Income", expense: "Spending", savings: "Savings" } as const;
const FIELD = "h-9 rounded-lg border border-field bg-surface px-2 text-[13px] text-ink";

export function TransactionsScreen() {
  const [filters, setFilters] = useState<TransactionFilters>({});
  const [dialogue, setDialogue] = useState<Dialogue | null>(null);
  const list = useTransactions(filters);
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const remove = useDeleteTransaction();

  function close() {
    setDialogue(null);
    create.reset();
    update.reset();
    remove.reset();
  }

  function setFilter<K extends keyof TransactionFilters>(
    key: K,
    value: TransactionFilters[K] | "",
  ) {
    setFilters((current) => {
      const next = { ...current, [key]: value };
      if (value === "") delete next[key];
      return next;
    });
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
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Transactions"
        intro="Everything you have logged or imported, newest first. The last 90 days are shown unless you pick dates."
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
      <Filters filters={filters} onChange={setFilter} onClear={() => setFilters({})} />
      <div className="mt-4">
        {list.isPending ? (
          <Skeleton lines={6} label="Loading transactions" />
        ) : list.isError ? (
          <ErrorState message={list.error.message} onRetry={() => list.refetch()} />
        ) : list.data.length === 0 ? (
          <EmptyState
            title="Nothing here yet"
            action={
              <Button onClick={() => setDialogue({ kind: "add" })}>
                Add your first transaction
              </Button>
            }
          >
            Add a transaction, or import a statement to bring in what you already have.
          </EmptyState>
        ) : (
          <>
            <p role="status" className="mb-2 text-[12px] text-ink-secondary">
              {plural(list.data.length, "transaction")}
            </p>
            <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
              {list.data.map((t) => (
                <Row
                  key={t.id}
                  txn={t}
                  onEdit={() => setDialogue({ kind: "edit", txn: t })}
                  onDelete={() => setDialogue({ kind: "delete", txn: t })}
                />
              ))}
            </ul>
          </>
        )}
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
                onClick={() => remove.mutate(dialogue.txn.id, { onSuccess: close })}
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

type FiltersProps = {
  filters: TransactionFilters;
  onChange: <K extends keyof TransactionFilters>(key: K, value: TransactionFilters[K] | "") => void;
  onClear: () => void;
};

function Filters({ filters, onChange, onClear }: FiltersProps) {
  const active = Object.keys(filters).length > 0;
  return (
    <form
      aria-label="Filter transactions"
      className="flex flex-wrap items-end gap-3 rounded-card border border-line bg-surface px-4 py-3"
      onSubmit={(event) => event.preventDefault()}
    >
      <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
        Type
        <select
          className={FIELD}
          value={filters.type ?? ""}
          onChange={(event) =>
            onChange("type", event.target.value as TransactionFilters["type"] | "")
          }
        >
          <option value="">All</option>
          {Object.entries(TYPE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
        Category
        <select
          className={FIELD}
          value={filters.category ?? ""}
          onChange={(event) => onChange("category", event.target.value)}
        >
          <option value="">All</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
        From
        <input
          type="date"
          className={FIELD}
          value={filters.start ?? ""}
          onChange={(event) => onChange("start", event.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
        To
        <input
          type="date"
          className={FIELD}
          value={filters.end ?? ""}
          onChange={(event) => onChange("end", event.target.value)}
        />
      </label>
      {active && (
        <Button variant="secondary" size="sm" onClick={onClear}>
          Clear filters
        </Button>
      )}
    </form>
  );
}

type RowProps = { txn: Transaction; onEdit: () => void; onDelete: () => void };

function Row({ txn, onEdit, onDelete }: RowProps) {
  const sign = txn.type === "income" ? "+" : "";
  const label = txn.description ?? txn.category;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
      <div className="min-w-[10rem] flex-1">
        <p className="break-words text-[14px] font-medium text-ink">{label}</p>
        <p className="text-[12px] text-ink-secondary">
          {formatDate(txn.date)} · {txn.category} · {TYPE_LABEL[txn.type]}
          {txn.is_bnpl && " · BNPL plan payment"}
        </p>
      </div>
      <span
        className={`text-[14px] font-semibold tabular-nums ${txn.type === "income" ? "text-success" : "text-ink"}`}
      >
        {sign}
        {formatRm(txn.amount_sen)}
      </span>
      {txn.bnpl_plan_id ? (
        <Link
          href="/plans"
          className="w-full text-right text-[12px] text-accent hover:underline sm:w-[8.5rem]"
        >
          Managed in Plans
        </Link>
      ) : (
        <div className="flex w-full justify-end gap-1 sm:w-[8.5rem]">
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
