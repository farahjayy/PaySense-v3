import { MoneyInput } from "@/components/ui/MoneyInput";
import { TextField } from "@/components/ui/fields";
import type { ProviderInfo } from "@/lib/api/queries";
import type { AmountMode, PlanDraft } from "@/lib/plans";

const SELECT = "h-10 rounded-lg border border-field bg-surface px-3 text-[14px] text-ink";

export type SetDraft = <K extends keyof PlanDraft>(key: K, value: PlanDraft[K]) => void;

type Props = {
  draft: PlanDraft;
  set: SetDraft;
  providers: readonly ProviderInfo[];
  /** Keeps element ids unique when two forms are on one page. */
  idPrefix?: string;
};

/** The purchase inputs shared by the plan form and the risk check: provider, item, dates, price. */
export function PlanFields({ draft, set, providers, idPrefix = "plan" }: Props) {
  const provider = providers.find((p) => p.key === draft.provider);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-provider`} className="text-xs font-medium text-ink-secondary">
          Provider
        </label>
        <select
          id={`${idPrefix}-provider`}
          className={SELECT}
          value={draft.provider}
          onChange={(event) => set("provider", event.target.value as PlanDraft["provider"])}
        >
          {providers.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      <TextField
        label="What are you buying?"
        required
        maxLength={80}
        value={draft.itemName}
        onChange={(event) => set("itemName", event.target.value)}
      />
      <TextField
        label="Purchase date"
        type="date"
        required
        value={draft.purchaseDate}
        onChange={(event) => set("purchaseDate", event.target.value)}
      />
      <TextField
        label="Number of instalments"
        inputMode="numeric"
        required
        value={draft.instalments}
        onChange={(event) => set("instalments", event.target.value)}
      />
      {provider?.rule_driven ? (
        <>
          <MoneyInput
            label="Price"
            required
            valueSen={draft.priceSen}
            onChange={(sen) => set("priceSen", sen)}
          />
          {provider.monthly_fee_applies && (
            <TextField
              label="Monthly fee (%)"
              inputMode="decimal"
              hint="The rate shown at your checkout. Leave 0 if there is none."
              value={draft.feePct}
              onChange={(event) => set("feePct", event.target.value)}
            />
          )}
        </>
      ) : (
        <ManualFields draft={draft} set={set} idPrefix={idPrefix} />
      )}
    </div>
  );
}

/** "Other provider": no rules are applied; the person types what their own checkout showed. */
function ManualFields({
  draft,
  set,
  idPrefix,
}: {
  draft: PlanDraft;
  set: SetDraft;
  idPrefix: string;
}) {
  return (
    <>
      <TextField
        label="Provider name"
        required
        maxLength={40}
        value={draft.providerLabel}
        onChange={(event) => set("providerLabel", event.target.value)}
      />
      <TextField
        label="First payment date"
        type="date"
        required
        value={draft.firstPaymentDate}
        onChange={(event) => set("firstPaymentDate", event.target.value)}
      />
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-mode`} className="text-xs font-medium text-ink-secondary">
          Your checkout shows
        </label>
        <select
          id={`${idPrefix}-mode`}
          className={SELECT}
          value={draft.amountMode}
          onChange={(event) => set("amountMode", event.target.value as AmountMode)}
        >
          <option value="instalment">The amount of each instalment</option>
          <option value="total">The total you will pay</option>
        </select>
      </div>
      <MoneyInput
        label={draft.amountMode === "instalment" ? "Each instalment" : "Total payable"}
        required
        valueSen={draft.amountSen}
        onChange={(sen) => set("amountSen", sen)}
      />
    </>
  );
}
