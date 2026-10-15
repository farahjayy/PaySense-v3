/** Calendar-month helpers for the month stepper. Months are "YYYY-MM" strings, like the API's. */

export function monthOf(date: string): string {
  return date.slice(0, 7);
}

export function currentMonth(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** The month `by` months after (or, if negative, before) `month`. */
export function shiftMonth(month: string, by: number): string {
  const index = Number(month.slice(0, 4)) * 12 + (Number(month.slice(5, 7)) - 1) + by;
  const year = Math.floor(index / 12);
  return `${year}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** First and last day of a month as ISO dates, the form the transactions endpoint takes. */
export function monthBounds(month: string): { start: string; end: string } {
  const year = Number(month.slice(0, 4));
  const number = Number(month.slice(5, 7));
  const lastDay = new Date(year, number, 0).getDate();
  return { start: `${month}-01`, end: `${month}-${String(lastDay).padStart(2, "0")}` };
}

/** Where to open: the latest month with anything logged in it, otherwise this month. */
export function startingMonth(months: readonly { month: string }[] | undefined, now: string) {
  if (!months || months.length === 0) return now;
  return months.reduce((latest, m) => (m.month > latest ? m.month : latest), months[0].month);
}
