import type { MonthSummary } from "@/lib/api/queries";
import { formatMonthCompact } from "@/lib/format";
import { formatRm } from "@/lib/money";

const SHOWN = 6;

/**
 * What actually happened in the latest months, straight from the ledger (no model involved). It is
 * sized to fit its card with no sideways scrolling: compact month names, tight columns.
 */
export function RecentMonths({ summary }: { summary: MonthSummary }) {
  const months = [...summary.months].sort((a, b) => b.month.localeCompare(a.month)).slice(0, SHOWN);
  if (months.length === 0) return null;
  return (
    <table className="w-full text-left text-[12px] tabular-nums sm:text-[13px]">
      <caption className="sr-only">Income, spending and net by month</caption>
      <thead className="text-[11px] uppercase tracking-wide text-ink-muted">
        <tr>
          <th scope="col" className="py-1.5 pr-2 font-medium">
            Month
          </th>
          <th scope="col" className="py-1.5 pr-2 text-right font-medium">
            Income
          </th>
          <th scope="col" className="py-1.5 pr-2 text-right font-medium">
            Spending
          </th>
          <th scope="col" className="py-1.5 text-right font-medium">
            Left over
          </th>
        </tr>
      </thead>
      <tbody>
        {months.map((m) => (
          <tr key={m.month} className="border-t border-line">
            <th scope="row" className="whitespace-nowrap py-1.5 pr-2 font-medium">
              {formatMonthCompact(m.month)}
            </th>
            <td className="whitespace-nowrap py-1.5 pr-2 text-right">{formatRm(m.income_sen)}</td>
            <td className="whitespace-nowrap py-1.5 pr-2 text-right">{formatRm(m.spend_sen)}</td>
            <td
              className={`whitespace-nowrap py-1.5 text-right font-semibold ${m.net_sen < 0 ? "text-danger" : "text-ink"}`}
            >
              {formatRm(m.net_sen)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
