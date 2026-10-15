"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Banner } from "@/components/ui/Banner";
import { TextField } from "@/components/ui/fields";
import { MoneyInput } from "@/components/ui/MoneyInput";
import type { Transaction, TransactionInput } from "@/lib/api/queries";
import { todayIso } from "@/lib/format";
import type { RowType } from "@/lib/import";

const TYPES: readonly { value: RowType; label: string }[] = [
  { value: "expense", label: "Spending" },
  { value: "income", label: "Income" },
  { value: "savings", label: "Savings" },
];

type Props = {
  initial?: Transaction;
  /** The names that can be chosen; the transaction's own category is added if it is not among them. */
  categories: readonly string[];
  saving: boolean;
  error: string | null;
  onSubmit: (input: TransactionInput) => void;
  onCancel: () => void;
};

/** Add or correct one transaction. Amounts are typed in ringgit and sent as whole sen. */
export function TransactionForm({
  initial,
  categories: choices,
  saving,
  error,
  onSubmit,
  onCancel,
}: Props) {
  const [date, setDate] = useState(initial?.date ?? todayIso());
  const [type, setType] = useState<RowType>(initial?.type ?? "expense");
  const [category, setCategory] = useState(initial?.category ?? choices[0] ?? "Other");
  const [amountSen, setAmountSen] = useState<number | null>(initial?.amount_sen ?? null);
  const [description, setDescription] = useState(initial?.description ?? "");

  const valid = date !== "" && amountSen !== null && amountSen > 0;
  const reason = date === "" ? "Choose a date." : "Enter an amount greater than zero.";
  const categories = choices.includes(category) ? choices : [...choices, category];

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || amountSen === null) return;
    onSubmit({
      date,
      amount_sen: amountSen,
      type,
      category,
      description: description.trim() === "" ? null : description.trim(),
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Date"
          type="date"
          required
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
        <MoneyInput label="Amount" required valueSen={amountSen} onChange={setAmountSen} />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="txn-type" className="text-xs font-medium text-ink-secondary">
            Type
          </label>
          <select
            id="txn-type"
            value={type}
            onChange={(event) => setType(event.target.value as RowType)}
            className="h-10 rounded-lg border border-field bg-surface px-3 text-[14px] text-ink"
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="txn-category" className="text-xs font-medium text-ink-secondary">
            Category
          </label>
          <select
            id="txn-category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-10 rounded-lg border border-field bg-surface px-3 text-[14px] text-ink"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>
      <TextField
        label="Description"
        maxLength={200}
        value={description}
        placeholder="Optional, e.g. Lunch at the cafe"
        onChange={(event) => setDescription(event.target.value)}
      />
      {error && (
        <Banner tone="danger" title="Not saved">
          {error}
        </Banner>
      )}
      {!valid && (
        <p id="txn-reason" className="text-[12px] text-ink-secondary">
          {reason}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button
          type="submit"
          variant="accent"
          disabled={!valid || saving}
          aria-describedby={valid ? undefined : "txn-reason"}
        >
          {saving ? "Saving…" : initial ? "Save changes" : "Add transaction"}
        </Button>
      </div>
    </form>
  );
}
