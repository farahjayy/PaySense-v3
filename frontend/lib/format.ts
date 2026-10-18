/** Display formatting. Pure; no money arithmetic (amounts arrive as integer sen). */

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_MONTH = /^(\d{4})-(\d{2})$/;

/** "2025-05-12" -> "12 May 2025". Read from the text, so no time zone can shift the day. */
export function formatDate(iso: string): string {
  const match = ISO_DATE.exec(iso);
  if (!match) return iso;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${Number(match[3])} ${month} ${match[1]}` : iso;
}

/** "2025-05" -> "May 2025"; with `short`, "May 25". */
export function formatMonth(key: string, short = false): string {
  const match = ISO_MONTH.exec(key);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  if (!match || !month) return key;
  return short
    ? `${month.slice(0, 3)} ${match[1].slice(2)}`
    : `${month} ${match[1]}`;
}

/** "2026-02" -> "Feb 2026": short enough for a narrow table column, with the year in full. */
export function formatMonthCompact(key: string): string {
  const match = ISO_MONTH.exec(key);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  return match && month ? `${month.slice(0, 3)} ${match[1]}` : key;
}

/** 0.234 -> "23%"; anything above 0 that rounds to 0 is "under 1%"; 1 is "100%". */
export function formatPercent(probability: number): string {
  const percent = Math.round(probability * 100);
  if (probability > 0 && percent === 0) return "under 1%";
  return `${percent}%`;
}

/** An added chance in percentage points: 0.134 -> "+13 points"; a real rise below 0.5 is never 0. */
export function formatPoints(added: number): string {
  const points = Math.round(added * 100);
  if (added > 0 && points === 0) return "+under 1 point";
  return `+${points} ${points === 1 ? "point" : "points"}`;
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export type Band = "Safe" | "Caution" | "At Risk";

export const BAND_COPY: Record<
  Band,
  { icon: string; tone: "success" | "warning" | "danger"; line: string }
> = {
  Safe: {
    icon: "✓",
    tone: "success",
    line: "Your income is likely to cover this on top of everything else.",
  },
  Caution: {
    icon: "!",
    tone: "warning",
    line: "It could work, but a bad month would leave you short.",
  },
  "At Risk": {
    icon: "▲",
    tone: "danger",
    line: "Your income is unlikely to cover this alongside your other commitments.",
  },
};

/** Today in the person's own time zone as "2026-10-09" (not UTC, which can be a day behind). */
export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
