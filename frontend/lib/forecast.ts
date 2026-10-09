/**
 * Reading the forecast response for display. Nothing here computes a probability, score or band:
 * those come from the server. This module only arranges what was sent (chart rows, a table
 * alternative) and turns data-quality fields into plain sentences the person can act on.
 */
import type { Forecast } from "@/lib/api/queries";
import { formatDate, formatMonth } from "@/lib/format";
import { formatRm } from "@/lib/money";

type Simulation = NonNullable<Forecast["simulation"]>;

export type MarginPoint = {
  month: string;
  label: string;
  /** Lower edge of the likely range, and its height above it (the area the chart shades). */
  low: number;
  spread: number;
  middle: number;
  high: number;
};

/** One point per month-end: where the running margin is likely to be (middle) and its range. */
export function marginPoints(sim: Simulation): MarginPoint[] {
  return sim.months.map((month, i) => {
    const low = sim.cumulative_margin_p10_sen[i];
    const high = sim.cumulative_margin_p90_sen[i];
    return {
      month,
      label: formatMonth(month, true),
      low,
      spread: high - low,
      middle: sim.cumulative_margin_p50_sen[i],
      high,
    };
  });
}

export type MarginTableRow = {
  month: string;
  monthLabel: string;
  monthly: string;
  cumulativeLow: string;
  cumulativeMiddle: string;
  cumulativeHigh: string;
  isWorst: boolean;
};

/** The same numbers as the chart, as text, for screen readers and anyone who prefers a table. */
export function marginTable(sim: Simulation): MarginTableRow[] {
  return sim.months.map((month, i) => ({
    month,
    monthLabel: formatMonth(month),
    monthly: formatRm(sim.monthly_margin_p50_sen[i]),
    cumulativeLow: formatRm(sim.cumulative_margin_p10_sen[i]),
    cumulativeMiddle: formatRm(sim.cumulative_margin_p50_sen[i]),
    cumulativeHigh: formatRm(sim.cumulative_margin_p90_sen[i]),
    isWorst: month === sim.worst_month,
  }));
}

/** A sentence that carries the chart's main message without the chart. */
export function chartSummary(sim: Simulation): string {
  const last = sim.months.length - 1;
  if (last < 0) return "No months to show.";
  const end = formatRm(sim.cumulative_margin_p50_sen[last]);
  const worst = sim.worst_month ? ` The tightest point is ${formatMonth(sim.worst_month)}.` : "";
  return `By ${formatMonth(sim.months[last])} your running margin is most likely about ${end}.${worst}`;
}

export type Notice = { id: string; tone: "info" | "warning"; title: string; body: string };

const BOOTSTRAP_NOTES: Partial<Record<Simulation["bootstrap"], string>> = {
  block:
    "The range of outcomes is based on a short record of how far past forecasts missed, so treat it as rough.",
  plain:
    "The range of outcomes is based on a short record of how far past forecasts missed, so treat it as rough.",
  fallback:
    "There was not enough history to measure how far past forecasts missed, so the range uses the overall spread of your weekly spending.",
  none: "No variation could be measured from your history, so the range may be narrower than real life.",
};

/** Everything that qualifies the number, in the order it matters. */
export function notices(forecast: Forecast): Notice[] {
  const out: Notice[] = [];
  if (forecast.is_stale && forecast.data_through) {
    out.push({
      id: "stale",
      tone: "warning",
      title: "Your ledger is out of date",
      body: `Your last logged day is ${formatDate(forecast.data_through)}${
        forecast.stale_days ? `, ${forecast.stale_days} days ago` : ""
      }. The forecast only knows what you logged up to then, so import or add what has happened since.`,
    });
  }
  for (const m of forecast.suspect_months) {
    out.push({
      id: `suspect-${m.month}`,
      tone: "warning",
      title: `${formatMonth(m.month)} looks incomplete`,
      body: m.detail,
    });
  }
  if (forecast.unmatched_items.length > 0) {
    out.push({
      id: "unmatched",
      tone: "info",
      title: "Some recurring items matched nothing",
      body: `${forecast.unmatched_items.join(", ")} did not match any logged transaction, so they are counted from their schedule alone. Check their matching text on the Recurring page.`,
    });
  }
  const sim = forecast.simulation;
  if (sim) {
    const note = BOOTSTRAP_NOTES[sim.bootstrap];
    if (note) out.push({ id: "bootstrap", tone: "info", title: "A rough range", body: note });
    if (sim.horizon_capped) {
      out.push({
        id: "capped",
        tone: "info",
        title: "Looking ahead is capped",
        body: "The forecast looks at most 52 weeks ahead, so anything beyond that is not included.",
      });
    }
  }
  return out;
}

/** What the headline band means for the month-by-month outlook (not for one purchase). */
export const OUTLOOK_LINE = {
  Safe: "On your recent pattern, your income is likely to cover your spending and commitments.",
  Caution: "Most months should work, but a bad one could leave you short.",
  "At Risk": "On your recent pattern, you are likely to run short at some point.",
} as const;
