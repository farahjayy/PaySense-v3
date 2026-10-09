import Link from "next/link";

import type { Bills } from "@/lib/api/queries";
import { formatDate, formatMonth } from "@/lib/format";
import { formatRm } from "@/lib/money";

const SHOWN = 5;

/** The unpaid instalments from this month on, soonest first. */
export function BillsDue({ bills }: { bills: Bills }) {
  const items = bills.months
    .flatMap((m) => m.items)
    .filter((i) => !i.is_paid)
    .sort((a, b) => a.due_date.localeCompare(b.due_date))
    .slice(0, SHOWN);
  const current = bills.months.find((m) => m.is_current);

  if (items.length === 0) {
    return (
      <p className="text-[13px] text-ink-secondary">No BNPL instalments are waiting to be paid.</p>
    );
  }
  return (
    <div>
      {current && (
        <p className="mb-2 text-[13px] text-ink-secondary">
          {formatMonth(current.month)}: {formatRm(current.paid_total_sen)} paid of{" "}
          {formatRm(current.total_due_sen)}
          {current.has_overdue && (
            <span className="font-medium text-danger"> · something is overdue</span>
          )}
        </p>
      )}
      <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
        {items.map((i) => (
          <li
            key={`${i.plan_id}-${i.seq}`}
            className="flex items-center justify-between gap-3 px-3.5 py-2.5 text-[13px]"
          >
            <div className="min-w-0">
              <p className="truncate font-medium text-ink">{i.item_name}</p>
              <p className="text-[12px] text-ink-secondary">
                {i.provider_label} · due {formatDate(i.due_date)}
              </p>
            </div>
            <span className="font-semibold tabular-nums">{formatRm(i.amount_sen)}</span>
          </li>
        ))}
      </ul>
      <Link
        href="/plans"
        className="mt-2 inline-block text-[13px] font-medium text-accent hover:underline"
      >
        All plans
      </Link>
    </div>
  );
}
