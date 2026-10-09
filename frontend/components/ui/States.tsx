import Link from "next/link";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { plural } from "@/lib/format";

const MONTHS_NEEDED = 4;

export function Skeleton({ lines = 3, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className="animate-pulse space-y-2.5">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-3.5 rounded bg-line"
          style={{ width: `${92 - ((i * 17) % 40)}%` }}
        />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

type EmptyProps = { title: string; children?: ReactNode; action?: ReactNode };

export function EmptyState({ title, children, action }: EmptyProps) {
  return (
    <div className="rounded-card border border-dashed border-line bg-surface-2 px-5 py-8 text-center">
      <p className="text-sm font-semibold text-ink">{title}</p>
      {children && (
        <p className="mx-auto mt-1 max-w-md text-[13px] text-ink-secondary">{children}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

type ErrorProps = { message: string; onRetry?: () => void };

export function ErrorState({ message, onRetry }: ErrorProps) {
  return (
    <div role="alert" className="rounded-card border border-danger/30 bg-danger-bg px-5 py-5">
      <p className="text-sm font-semibold text-danger">That did not load</p>
      <p className="mt-1 text-[13px] text-ink-secondary">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

type LockedProps = {
  reason: "needs_four_months" | "no_usable_history" | null;
  monthsOfHistory: number;
};

/**
 * The forecast needs about four months of history. This is a normal first-run state, not an error:
 * it says what is missing and where to fix it.
 */
export function LockedState({ reason, monthsOfHistory }: LockedProps) {
  const noUsable = reason === "no_usable_history";
  const shown = Math.min(monthsOfHistory, MONTHS_NEEDED);
  // Four months are logged but the weekly pattern still has fewer than 17 complete weeks.
  const needsWeeks = !noUsable && monthsOfHistory >= MONTHS_NEEDED;
  return (
    <div className="rounded-card border border-line bg-surface px-5 py-6 sm:px-7">
      <p className="text-sm font-semibold text-ink">
        {noUsable
          ? "There is nothing to forecast from yet"
          : needsWeeks
            ? "Almost there: the forecast needs a few more complete weeks"
            : "Your forecast unlocks with four months of history"}
      </p>
      <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-ink-secondary">
        {noUsable
          ? "What you have logged so far is savings, BNPL payments or items you have already marked as recurring. Add your everyday spending and income to build a forecast."
          : needsWeeks
            ? "You have four months logged, but the forecast learns from at least 17 complete weeks (Monday to Sunday) of spending and income. Import or add a little more history, going further back if you can."
            : "A forecast built on less than that would look precise and be wrong. Import a bank statement to start from the history you already have."}
      </p>
      {!noUsable && (
        <div className="mt-4 max-w-xs">
          <div
            role="progressbar"
            aria-label="Months of history"
            aria-valuemin={0}
            aria-valuemax={MONTHS_NEEDED}
            aria-valuenow={shown}
            aria-valuetext={`${plural(shown, "month")} of ${MONTHS_NEEDED}`}
            className="h-2 overflow-hidden rounded-full bg-line"
          >
            <div
              className="h-full rounded-full bg-accent"
              style={{ width: `${(shown / MONTHS_NEEDED) * 100}%` }}
            />
          </div>
          <p className="mt-1.5 text-[12px] text-ink-secondary">
            {plural(shown, "month")} of {MONTHS_NEEDED} logged
          </p>
        </div>
      )}
      <Link
        href="/import"
        className="mt-5 inline-flex h-10 items-center rounded-lg bg-accent px-4 text-[13px] font-semibold text-white hover:bg-accent/90"
      >
        Import a statement
      </Link>
    </div>
  );
}
