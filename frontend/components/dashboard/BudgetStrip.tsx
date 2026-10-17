"use client";

import Link from "next/link";

import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useBudgetStatus } from "@/lib/api/topic";
import { barPercent, spentOfLimit, STATE_COPY } from "@/lib/budgets";

const SHOWN = 4;

/** This month's budgets at a glance (WP7); the full page is /budgets. Figures from the server. */
export function BudgetStrip() {
  const status = useBudgetStatus();
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <CardTitle>Budgets this month</CardTitle>
        <Link href="/budgets" className="text-[13px] font-medium text-accent hover:underline">
          All budgets
        </Link>
      </div>
      {status.isPending ? (
        <Skeleton lines={3} label="Loading budgets" />
      ) : status.isError ? (
        <ErrorState message={status.error.message} onRetry={() => status.refetch()} />
      ) : status.data.items.length === 0 ? (
        <CardCaption>
          No budgets yet.{" "}
          <Link href="/budgets" className="font-medium text-accent hover:underline">
            Set a budget
          </Link>{" "}
          for a category and PaySense tells you when you are close.
        </CardCaption>
      ) : (
        <ul className="mt-3 space-y-3">
          {status.data.items.slice(0, SHOWN).map((item) => {
            const copy = STATE_COPY[item.state];
            return (
              <li key={item.category}>
                <div className="flex items-baseline justify-between gap-2 text-[13px]">
                  <span className="font-medium text-ink">{item.category}</span>
                  <span className={copy.text}>
                    <span aria-hidden>{copy.glyph} </span>
                    {copy.label}
                  </span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-surface-2" aria-hidden>
                  <div
                    className={`h-1.5 rounded-full ${copy.bar}`}
                    style={{ width: `${barPercent(item.percent)}%` }}
                  />
                </div>
                <p className="mt-0.5 text-[12px] text-ink-secondary">
                  {spentOfLimit(item.spent_sen, item.limit_sen)}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
