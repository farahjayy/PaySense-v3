/**
 * Money on the frontend (ADR D-16, D-29). The API speaks integer sen; this module is the only
 * place a person's typed ringgit becomes sen, and sen becomes display text. Amounts are read from
 * the TEXT — never `parseFloat(x) * 100` — so 19.99 is 1999 and not 1998.999…
 *
 * Mirrors backend/app/domain/money.py; backend/tests/domain/test_money.py and
 * tests/unit/money.test.ts carry the same cases.
 */

const SEN_PER_RM = 100;
// Optional "RM", then 1,234 or 1234, then an optional .5 or .50 — nothing else (no sign, no
// parentheses, no third decimal): a guessed amount is worse than a rejected one.
const RM_TEXT = /^(?:RM\s*)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?$/i;

/** Ringgit text -> integer sen, or null if it is not an unambiguous amount. */
export function parseRm(text: string): number | null {
  const match = RM_TEXT.exec(text.trim());
  if (!match) return null;
  const whole = Number(match[1].replace(/,/g, ""));
  const cents = Number((match[2] ?? "0").padEnd(2, "0"));
  const sen = whole * SEN_PER_RM + cents;
  return Number.isSafeInteger(sen) ? sen : null;
}

/** Integer sen -> "RM 1,234.56" (negative: "-RM 2.50"). */
export function formatRm(sen: number): string {
  if (!Number.isSafeInteger(sen)) {
    throw new RangeError(`money must be a whole, safe number of sen, got ${sen}`);
  }
  const absolute = Math.abs(sen);
  const whole = Math.floor(absolute / SEN_PER_RM);
  const cents = String(absolute % SEN_PER_RM).padStart(2, "0");
  const grouped = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sen < 0 ? "-" : ""}RM ${grouped}.${cents}`;
}

/**
 * A short label for a chart's money axis: "RM 650", "-RM 1.3k". The space is a no-break space,
 * because the chart wraps a label at a normal space and the halves overlap the month labels.
 */
export function formatAxisRm(sen: number): string {
  const rm = sen / SEN_PER_RM;
  const abs = Math.abs(rm);
  const text =
    abs >= 1000 ? `${(abs / 1000).toFixed(1).replace(/\.0$/, "")}k` : `${Math.round(abs)}`;
  return `${rm < 0 ? "-" : ""}RM ${text}`;
}
