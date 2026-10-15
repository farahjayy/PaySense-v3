"use client";

import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import type { CategorySummary } from "@/lib/api/queries";
import { formatMonth, formatPercent } from "@/lib/format";
import { formatRm } from "@/lib/money";

type Props = {
  month: string;
  summary: CategorySummary | undefined;
  isPending: boolean;
  error: string | null;
  selected: string | undefined;
  onSelect: (category: string | undefined) => void;
};

/**
 * Where the month's spending went. Every figure is the server's (the same definition of "spent"
 * as the dashboard); a category is a button, so picking one filters the list beside it.
 */
export function CategorySpending({ month, summary, isPending, error, selected, onSelect }: Props) {
  const label = formatMonth(month);
  return (
    <Card>
      <CardTitle>Spending by category</CardTitle>
      <CardCaption>{label}</CardCaption>
      <div className="mt-4">
        {isPending ? (
          <Skeleton lines={5} label="Loading spending by category" />
        ) : error !== null || !summary ? (
          <p role="alert" className="text-[13px] text-danger">
            {error ?? "Spending by category did not load."}
          </p>
        ) : summary.categories.length === 0 ? (
          <p className="text-[13px] text-ink-secondary">Nothing spent in {label}.</p>
        ) : (
          <ul className="space-y-1">
            {summary.categories.map((c) => (
              <li key={c.category}>
                <button
                  type="button"
                  aria-pressed={selected === c.category}
                  onClick={() => onSelect(selected === c.category ? undefined : c.category)}
                  className={`block w-full rounded-lg px-2 py-1.5 text-left hover:bg-surface-2 ${
                    selected === c.category ? "bg-accent-bg" : ""
                  }`}
                >
                  <span className="flex items-baseline justify-between gap-3 text-[13px]">
                    <span className="font-medium text-ink">{c.category}</span>
                    <span className="tabular-nums text-ink-secondary">
                      <span className="text-ink">{formatRm(c.spend_sen)}</span>
                      {" · "}
                      <span>{formatPercent(c.share)}</span>
                    </span>
                  </span>
                  <span aria-hidden className="mt-1 block h-1.5 rounded-full bg-line">
                    <span
                      className="block h-1.5 rounded-full bg-accent"
                      style={{ width: `${Math.max(c.share * 100, 2)}%` }}
                    />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {summary && (
        <div
          role="group"
          aria-label={`Totals for ${label}`}
          className="mt-4 border-t border-line pt-3 text-[12px] text-ink-secondary"
        >
          <dl className="space-y-1">
            <Total label="Income" sen={summary.income_sen} />
            {summary.refund_sen > 0 && (
              <Total label="Before refunds" sen={summary.gross_spend_sen} />
            )}
            <Total label="Spent" sen={summary.spend_sen} />
            {summary.savings_sen > 0 && <Total label="Saved" sen={summary.savings_sen} />}
            {summary.refund_sen > 0 && <Total label="Refunded" sen={summary.refund_sen} />}
          </dl>
        </div>
      )}
    </Card>
  );
}

function Total({ label, sen }: { label: string; sen: number }) {
  return (
    <div className="flex justify-between gap-3">
      <dt>{label}</dt>
      <dd className="tabular-nums text-ink">{formatRm(sen)}</dd>
    </div>
  );
}
