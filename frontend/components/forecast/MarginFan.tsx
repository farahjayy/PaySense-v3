"use client";

import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Forecast } from "@/lib/api/queries";
import { chartSummary, marginPoints, marginTable } from "@/lib/forecast";
import { formatRm } from "@/lib/money";

type Simulation = NonNullable<Forecast["simulation"]>;

/** Compact axis labels: "RM 1.2k" is readable at a glance; the table has the exact figures. */
function axisLabel(sen: number): string {
  const rm = sen / 100;
  const abs = Math.abs(rm);
  const text =
    abs >= 1000 ? `${(abs / 1000).toFixed(1).replace(/\.0$/, "")}k` : `${Math.round(abs)}`;
  return `${rm < 0 ? "-" : ""}RM ${text}`;
}

/**
 * Running margin month by month: the line is the most likely total, the shaded band is where it
 * lands in 8 of 10 simulated futures, and below the zero line means short of money. The chart is
 * decoration for the table beneath it, which carries the same numbers.
 */
export function MarginFan({ simulation }: { simulation: Simulation }) {
  const points = marginPoints(simulation);
  const rows = marginTable(simulation);
  return (
    <figure className="m-0">
      <div role="img" aria-label={chartSummary(simulation)} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            accessibilityLayer={false}
            data={points}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: "var(--color-line)" }}
              tick={{ fontSize: 12, fill: "var(--color-ink-secondary)" }}
            />
            <YAxis
              width={64}
              tickLine={false}
              axisLine={false}
              tickFormatter={axisLabel}
              tick={{ fontSize: 12, fill: "var(--color-ink-secondary)" }}
            />
            <ReferenceLine y={0} stroke="var(--color-danger)" strokeDasharray="4 3" />
            <Area
              dataKey="low"
              stackId="range"
              stroke="none"
              fill="transparent"
              isAnimationActive={false}
              legendType="none"
            />
            <Area
              dataKey="spread"
              stackId="range"
              stroke="var(--color-chart-edge)"
              strokeOpacity={0.6}
              fill="var(--color-chart-blue)"
              fillOpacity={0.35}
              isAnimationActive={false}
            />
            <Line
              dataKey="middle"
              stroke="var(--color-accent)"
              strokeWidth={2.5}
              dot={{ r: 3, fill: "var(--color-accent)" }}
              isAnimationActive={false}
            />
            <Tooltip
              formatter={(value, name) =>
                name === "spread" || name === "low" ? [] : [formatRm(Number(value)), "Most likely"]
              }
              contentStyle={{
                borderRadius: 8,
                border: "1px solid var(--color-line)",
                fontSize: 12,
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-2 space-y-0.5 text-[12px] leading-relaxed text-ink-secondary">
        <p>The line is the most likely total for each month-end.</p>
        <p>The shaded area is where the total lands in 8 out of 10 simulated futures.</p>
        <p>Below the dashed line (RM 0) you would be short of money.</p>
      </figcaption>
      <details className="mt-3 rounded-lg border border-line bg-surface-2 px-4 py-2.5 text-[13px]">
        <summary className="cursor-pointer font-medium text-ink">Show the numbers</summary>
        <div
          className="mt-3 overflow-x-auto"
          role="region"
          aria-label="Forecast numbers, scrollable"
          tabIndex={0}
        >
          <table className="w-full min-w-[30rem] text-left tabular-nums">
            <caption className="sr-only">Forecast running margin by month</caption>
            <thead className="text-[11px] uppercase tracking-wide text-ink-muted">
              <tr>
                <th scope="col" className="py-1.5 pr-3 font-medium">
                  Month
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  This month alone
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Total so far, bad case
                </th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">
                  Total so far, typical
                </th>
                <th scope="col" className="py-1.5 text-right font-medium">
                  Total so far, good case
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.month} className="border-t border-line">
                  <th scope="row" className="py-1.5 pr-3 font-medium">
                    {r.monthLabel}
                    {r.isWorst && <span className="ml-1.5 text-[11px] text-warning">tightest</span>}
                  </th>
                  <td className="py-1.5 pr-3 text-right">{r.monthly}</td>
                  <td className="py-1.5 pr-3 text-right">{r.cumulativeLow}</td>
                  <td className="py-1.5 pr-3 text-right">{r.cumulativeMiddle}</td>
                  <td className="py-1.5 text-right">{r.cumulativeHigh}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-ink-secondary">
          Each figure is a typical value worked out on its own, so the columns do not add up line
          by line: the typical total is not the sum of the typical months.
        </p>
      </details>
    </figure>
  );
}
