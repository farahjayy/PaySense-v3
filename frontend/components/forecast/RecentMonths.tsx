import type { MonthSummary } from "@/lib/api/queries";
import { formatMonth } from "@/lib/format";
import { formatRm } from "@/lib/money";

const SHOWN = 6;

/** What actually happened in the latest months, straight from the ledger (no model involved). */
export function RecentMonths({ summary }: { summary: MonthSummary }) {
  const months = [...summary.months].sort((a, b) => b.month.localeCompare(a.month)).slice(0, SHOWN);
  if (months.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[26rem] text-left text-[13px] tabular-nums">
        <caption className="sr-only">Income, spending and net by month</caption>
        <thead className="text-[11px] uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Month
            </th>
            <th scope="col" className="py-1.5 pr-3 text-right font-medium">
              Income
            </th>
            <th scope="col" className="py-1.5 pr-3 text-right font-medium">
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
              <th scope="row" className="py-1.5 pr-3 font-medium">
                {formatMonth(m.month)}
              </th>
              <td className="py-1.5 pr-3 text-right">{formatRm(m.income_sen)}</td>
              <td className="py-1.5 pr-3 text-right">{formatRm(m.spend_sen)}</td>
              <td
                className={`py-1.5 text-right font-semibold ${m.net_sen < 0 ? "text-danger" : "text-ink"}`}
              >
                {formatRm(m.net_sen)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
