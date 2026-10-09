"use client";

import { formatDate } from "@/lib/format";
import { CATEGORIES, type ReviewRow, type RowType } from "@/lib/import";
import { formatRm } from "@/lib/money";

type Patch = Partial<Pick<ReviewRow, "category" | "type" | "include">>;
type Props = {
  rows: readonly ReviewRow[];
  onChange: (row: number, patch: Patch) => void;
};

const TYPES: readonly { value: RowType; label: string }[] = [
  { value: "expense", label: "Spending" },
  { value: "income", label: "Income" },
  { value: "savings", label: "Savings" },
];

const SELECT =
  "h-9 w-full rounded-lg border border-field bg-surface px-2 text-[13px] text-ink hover:border-ink-muted";

/** One line per statement row: a card on a phone, a table-like row from tablet width up. */
export function ReviewList({ rows, onChange }: Props) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
      {rows.map((r) => (
        <li
          key={r.row}
          className={`grid gap-x-3 gap-y-2 px-4 py-3 md:grid-cols-[auto_6.5rem_minmax(0,1fr)_8rem_8rem_7rem] md:items-center ${
            r.include ? "" : "bg-surface-2 text-ink-muted"
          }`}
        >
          <input
            type="checkbox"
            checked={r.include}
            onChange={(event) => onChange(r.row, { include: event.target.checked })}
            aria-label={`Include row ${r.row}: ${r.description || "no description"}, ${formatDate(r.date)}`}
            className="h-5 w-5 accent-[var(--color-accent)]"
          />
          <span className="text-[13px] tabular-nums">{formatDate(r.date)}</span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium">{r.description || "No description"}</p>
            {(r.duplicate || r.issues.length > 0) && (
              <p className="mt-0.5 text-[12px] text-warning">
                {r.duplicate && "Already in your ledger. "}
                {r.issues.join(". ")}
              </p>
            )}
          </div>
          <select
            aria-label={`Category for row ${r.row}`}
            className={SELECT}
            value={r.category}
            onChange={(event) => onChange(r.row, { category: event.target.value })}
          >
            {!CATEGORIES.includes(r.category as (typeof CATEGORIES)[number]) && (
              <option value={r.category}>{r.category}</option>
            )}
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            aria-label={`Type for row ${r.row}`}
            className={SELECT}
            value={r.type}
            onChange={(event) => onChange(r.row, { type: event.target.value as RowType })}
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <span className="text-[14px] font-semibold tabular-nums md:text-right">
            {formatRm(r.amountSen)}
          </span>
        </li>
      ))}
    </ul>
  );
}
