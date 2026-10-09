/**
 * Turning the plan form into the request the API expects. The server owns every rule (start dates,
 * fees, the limit split); this only decides which fields apply to the chosen provider so the
 * request is one the server accepts.
 */
import type { PlanInput, ProviderInfo } from "@/lib/api/queries";

export type AmountMode = "instalment" | "total";

export type PlanDraft = {
  provider: PlanInput["provider"];
  itemName: string;
  purchaseDate: string;
  instalments: string;
  priceSen: number | null;
  feePct: string;
  firstPaymentDate: string;
  providerLabel: string;
  amountMode: AmountMode;
  amountSen: number | null;
};

export const MAX_INSTALMENTS = 36;

export function emptyDraft(today: string): PlanDraft {
  return {
    provider: "spaylater",
    itemName: "",
    purchaseDate: today,
    instalments: "3",
    priceSen: null,
    feePct: "0",
    firstPaymentDate: "",
    providerLabel: "",
    amountMode: "instalment",
    amountSen: null,
  };
}

function wholeCount(text: string): number | null {
  const n = Number(text);
  return Number.isInteger(n) && n >= 1 && n <= MAX_INSTALMENTS ? n : null;
}

function percent(text: string): number | null {
  if (text.trim() === "") return 0;
  const n = Number(text);
  return Number.isFinite(n) && n >= 0 && n <= 30 ? n : null;
}

/** The request for this draft, or null while something the provider needs is still missing. */
export function toPlanInput(
  draft: PlanDraft,
  provider: ProviderInfo | undefined,
): PlanInput | null {
  const count = wholeCount(draft.instalments);
  const name = draft.itemName.trim();
  if (!provider || count === null || name === "" || draft.purchaseDate === "") return null;

  if (provider.rule_driven) {
    const fee = provider.monthly_fee_applies ? percent(draft.feePct) : 0;
    if (draft.priceSen === null || draft.priceSen <= 0 || fee === null) return null;
    return {
      provider: draft.provider,
      item_name: name,
      purchase_date: draft.purchaseDate,
      num_installments: count,
      total_price_sen: draft.priceSen,
      monthly_fee_rate_pct: fee,
    };
  }

  const label = draft.providerLabel.trim();
  if (
    label === "" ||
    draft.firstPaymentDate === "" ||
    draft.amountSen === null ||
    draft.amountSen <= 0
  ) {
    return null;
  }
  return {
    provider: draft.provider,
    item_name: name,
    purchase_date: draft.purchaseDate,
    num_installments: count,
    monthly_fee_rate_pct: 0,
    first_payment_date: draft.firstPaymentDate,
    provider_label: label,
    ...(draft.amountMode === "instalment"
      ? { instalment_sen: draft.amountSen }
      : { total_payable_sen: draft.amountSen }),
  };
}
