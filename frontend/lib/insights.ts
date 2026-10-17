/** Display helpers for insights and recommendations (WP3). Pure; figures arrive from the server. */

import { formatDate, formatPercent } from "@/lib/format";
import { formatRm } from "@/lib/money";

export const SEVERITY_COPY = {
  high: { label: "Needs attention", glyph: "▲", text: "text-danger" },
  medium: { label: "Worth a look", glyph: "!", text: "text-warning" },
  low: { label: "Tip", glyph: "i", text: "text-accent" },
} as const;

export const STATUS_COPY = {
  new: "new",
  gone: "none this month",
  up: "up",
  down: "down",
  same: "same",
} as const;

type Change = {
  status: keyof typeof STATUS_COPY;
  change_sen: number;
  change_pct: number | null;
  previous_sen: number;
  spend_sen: number;
};

/** "up RM 100.00 (50%) on the month before" and the like. */
export function changeLine(c: Change): string {
  if (c.status === "new") return `new: ${formatRm(c.spend_sen)}`;
  if (c.status === "gone") return `none this month (was ${formatRm(c.previous_sen)})`;
  if (c.status === "same") return "the same as the month before";
  const pct = c.change_pct === null ? "" : ` (${formatPercent(Math.abs(c.change_pct))})`;
  const word = c.status === "up" ? "up" : "down";
  return `${word} ${formatRm(Math.abs(c.change_sen))}${pct} on the month before`;
}

type Source = { value: number | string; unit: string };

/** A recommendation's source figure, written the way its sentence writes it. */
export function formatSource(source: Source): string {
  const { value, unit } = source;
  if (unit === "sen" && typeof value === "number") return formatRm(value);
  if ((unit === "probability" || unit === "percent") && typeof value === "number") {
    return formatPercent(value);
  }
  if (unit === "date" && typeof value === "string") return formatDate(value);
  return String(value);
}
