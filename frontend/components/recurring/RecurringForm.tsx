"use client";

import { useState } from "react";

import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/fields";
import { MoneyInput } from "@/components/ui/MoneyInput";
import type { RecurringInput, RecurringItem } from "@/lib/api/queries";
import { todayIso } from "@/lib/format";

export const CADENCE_LABEL = {
  weekly: "Every week",
  biweekly: "Every two weeks",
  monthly: "Every month",
  semester: "Every semester",
  custom: "Every few days",
} as const;

type Props = {
  initial?: RecurringItem;
  saving: boolean;
  error: string | null;
  onSubmit: (input: RecurringInput) => void;
  onCancel: () => void;
};

const SELECT = "h-10 rounded-lg border border-field bg-surface px-3 text-[14px] text-ink";

/** A bill or income that repeats. The first date is when it last (or next) lands. */
export function RecurringForm({ initial, saving, error, onSubmit, onCancel }: Props) {
  const [kind, setKind] = useState<RecurringInput["kind"]>(initial?.kind ?? "bill");
  const [name, setName] = useState(initial?.name ?? "");
  const [amountSen, setAmountSen] = useState<number | null>(initial?.amount_sen ?? null);
  const [cadence, setCadence] = useState<RecurringInput["cadence"]>(initial?.cadence ?? "monthly");
  const [intervalText, setIntervalText] = useState(String(initial?.custom_interval_days ?? ""));
  const [anchor, setAnchor] = useState(initial?.anchor_date ?? todayIso());

  const days = Number(intervalText);
  const customOk = cadence !== "custom" || (Number.isInteger(days) && days >= 1 && days <= 366);
  const valid =
    /\p{L}/u.test(name) && amountSen !== null && amountSen > 0 && anchor !== "" && customOk;

  const reason = !/\p{L}/u.test(name)
    ? "Give it a name with some letters, such as Rent or Netflix."
    : amountSen === null || amountSen <= 0
      ? "Enter an amount greater than zero."
      : anchor === ""
        ? "Choose a date."
        : "Enter a whole number of days from 1 to 366.";

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || amountSen === null) return;
    onSubmit({
      kind,
      name: name.trim(),
      amount_sen: amountSen,
      cadence,
      custom_interval_days: cadence === "custom" ? days : null,
      anchor_date: anchor,
      active: initial?.active ?? true,
      origin: initial?.origin ?? "manual",
      match_text: initial?.match_text ?? null,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="rec-kind" className="text-xs font-medium text-ink-secondary">
            What is it?
          </label>
          <select
            id="rec-kind"
            className={SELECT}
            value={kind}
            disabled={Boolean(initial)}
            onChange={(event) => setKind(event.target.value as RecurringInput["kind"])}
          >
            <option value="bill">A bill I pay</option>
            <option value="income">Income I receive</option>
          </select>
        </div>
        <TextField
          label="Name"
          required
          maxLength={80}
          value={name}
          hint="Include some letters, e.g. Rent or Netflix."
          onChange={(event) => setName(event.target.value)}
        />
        <MoneyInput label="Amount" required valueSen={amountSen} onChange={setAmountSen} />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="rec-cadence" className="text-xs font-medium text-ink-secondary">
            How often
          </label>
          <select
            id="rec-cadence"
            className={SELECT}
            value={cadence}
            onChange={(event) => setCadence(event.target.value as RecurringInput["cadence"])}
          >
            {Object.entries(CADENCE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {cadence === "custom" && (
          <TextField
            label="Number of days between"
            inputMode="numeric"
            value={intervalText}
            error={intervalText !== "" && !customOk ? "Enter a whole number from 1 to 366." : null}
            onChange={(event) => setIntervalText(event.target.value)}
          />
        )}
        <TextField
          label="A date it landed or will land"
          type="date"
          required
          value={anchor}
          onChange={(event) => setAnchor(event.target.value)}
        />
      </div>
      {error && (
        <Banner tone="danger" title="Not saved">
          {error}
        </Banner>
      )}
      {!valid && (
        <p id="rec-reason" className="text-[12px] text-ink-secondary">
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
          aria-describedby={valid ? undefined : "rec-reason"}
        >
          {saving ? "Saving…" : initial ? "Save changes" : "Add"}
        </Button>
      </div>
    </form>
  );
}
