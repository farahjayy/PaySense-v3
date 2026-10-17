"use client";

import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RiskCheck } from "@/lib/api/queries";
import { formatMonth } from "@/lib/format";
import { formatAxisRm, formatRm } from "@/lib/money";

type Curve = NonNullable<RiskCheck["with_plan_curve"]>;
type Props = { withPlan: Curve; without: Curve };

/** Most likely running margin with and without this purchase; the gap between the lines is its cost. */
export function WithWithoutChart({ withPlan, without }: Props) {
  const points = withPlan.months.map((month, i) => ({
    label: formatMonth(month, true),
    without: without.cumulative_p50_sen[i],
    withPlan: withPlan.cumulative_p50_sen[i],
    bad: withPlan.cumulative_p10_sen[i],
  }));
  const lastIndex = withPlan.months.length - 1;
  const summary =
    lastIndex < 0
      ? "No months to show."
      : `By ${formatMonth(withPlan.months[lastIndex])} your running margin is most likely about ${formatRm(
          withPlan.cumulative_p50_sen[lastIndex],
        )} with this purchase, against ${formatRm(without.cumulative_p50_sen[lastIndex])} without it.`;

  return (
    <figure className="m-0">
      <div role="img" aria-label={summary} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            accessibilityLayer={false}
            data={points}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              tick={{ fontSize: 12, fill: "var(--color-ink-secondary)" }}
            />
            <YAxis
              width={76}
              tickLine={false}
              axisLine={false}
              tickFormatter={formatAxisRm}
              tick={{ fontSize: 12, fill: "var(--color-ink-secondary)" }}
            />
            <ReferenceLine y={0} stroke="var(--color-danger)" strokeDasharray="4 3" />
            <Line
              dataKey="without"
              stroke="var(--color-ink-muted)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              dataKey="withPlan"
              stroke="var(--color-accent)"
              strokeWidth={2.5}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="bad"
              stroke="var(--color-danger)"
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            />
            <Tooltip formatter={(value) => formatRm(Number(value))} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-2 text-[12px] leading-relaxed text-ink-secondary">
        Grey: without this purchase. Blue: with it. Dashed red: a bad run of months with it. Below
        the dashed zero line you would be short.
      </figcaption>
      <details className="mt-3 rounded-lg border border-line bg-surface-2 px-4 py-2.5 text-[13px]">
        <summary className="cursor-pointer font-medium text-ink">Show the numbers</summary>
        <div
          className="mt-3 overflow-x-auto"
          role="region"
          aria-label="Margin with and without the purchase, scrollable"
          tabIndex={0}
        >
          <table className="w-full min-w-[30rem] text-left tabular-nums">
            <caption className="sr-only">
              Running margin by month, with and without the purchase
            </caption>
            <thead className="text-[11px] uppercase tracking-wide text-ink-muted">
              <tr>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Month
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Without
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  With
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  With, bad run
                </th>
              </tr>
            </thead>
            <tbody>
              {withPlan.months.map((month, i) => (
                <tr key={month} className="border-t border-line">
                  <th scope="row" className="py-1.5 pr-3 font-medium">
                    {formatMonth(month)}
                  </th>
                  <td className="py-1.5 pr-3 text-right">
                    {formatRm(without.cumulative_p50_sen[i])}
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    {formatRm(withPlan.cumulative_p50_sen[i])}
                  </td>
                  <td className="py-1.5 text-right">{formatRm(withPlan.cumulative_p10_sen[i])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
