/**
 * Arranging a risk-check response for display. No probability, band or sentence is made here: the
 * server sends them. This module only reshapes (notices, the form prefilled from a suggestion).
 */
import type { PlanInput, RiskCheck } from "@/lib/api/queries";
import { formatMonth } from "@/lib/format";
import type { Notice } from "@/lib/forecast";
import { emptyDraft, type PlanDraft } from "@/lib/plans";

/** The server flags a ledger as stale after this many days; the check carries the age only. */
const STALE_AFTER_DAYS = 14;

export function riskNotices(check: RiskCheck): Notice[] {
  const out: Notice[] = [];
  if (check.stale_days !== null && check.stale_days > STALE_AFTER_DAYS) {
    out.push({
      id: "stale",
      tone: "warning",
      title: "Your ledger is out of date",
      body: `Your last logged day was ${check.stale_days} days ago. The check only knows what you logged up to then, so import or add what has happened since.`,
    });
  }
  for (const m of check.suspect_months) {
    out.push({
      id: `suspect-${m.month}`,
      tone: "warning",
      title: `${formatMonth(m.month)} looks incomplete`,
      body: m.detail,
    });
  }
  if (check.unmatched_items.length > 0) {
    out.push({
      id: "unmatched",
      tone: "info",
      title: "Some recurring items matched nothing",
      body: `${check.unmatched_items.join(", ")} did not match any logged transaction, so they are counted from their schedule alone.`,
    });
  }
  return out;
}

/** The form state that produces `input`; used to try a suggested change. */
export function draftFromInput(input: PlanInput, today: string): PlanDraft {
  const base = emptyDraft(today);
  return {
    ...base,
    provider: input.provider,
    itemName: input.item_name,
    purchaseDate: input.purchase_date,
    instalments: String(input.num_installments),
    priceSen: input.total_price_sen ?? null,
    feePct: String(input.monthly_fee_rate_pct ?? 0),
    firstPaymentDate: input.first_payment_date ?? "",
    providerLabel: input.provider_label ?? "",
    amountMode: input.total_payable_sen != null ? "total" : "instalment",
    amountSen: input.total_payable_sen ?? input.instalment_sen ?? null,
  };
}
