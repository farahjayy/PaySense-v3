"use client";

import { formatMonth } from "@/lib/format";
import { shiftMonth } from "@/lib/months";

type Props = { month: string; min: string; max: string; onChange: (month: string) => void };

const STEP =
  "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-field bg-surface text-[16px] text-ink hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40";

/** One calendar month at a time, between the first month with data and this month. */
export function MonthStepper({ month, min, max, onChange }: Props) {
  return (
    <div role="group" aria-label="Month" className="inline-flex items-center gap-1.5">
      <button
        type="button"
        aria-label="Previous month"
        disabled={month <= min}
        onClick={() => onChange(shiftMonth(month, -1))}
        className={STEP}
      >
        <span aria-hidden>‹</span>
      </button>
      <span
        aria-live="polite"
        className="min-w-[8.5rem] text-center text-[14px] font-semibold text-ink"
      >
        {formatMonth(month)}
      </span>
      <button
        type="button"
        aria-label="Next month"
        disabled={month >= max}
        onClick={() => onChange(shiftMonth(month, 1))}
        className={STEP}
      >
        <span aria-hidden>›</span>
      </button>
    </div>
  );
}
