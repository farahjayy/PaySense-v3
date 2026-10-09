"use client";

import { useEffect, useMemo, useState } from "react";

import { PlanPreviewPanel } from "@/components/plans/PlanPreviewPanel";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/fields";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { useCreatePlan, usePreviewPlan, useProviders, type PlanInput } from "@/lib/api/queries";
import { todayIso } from "@/lib/format";
import { emptyDraft, toPlanInput, type AmountMode, type PlanDraft } from "@/lib/plans";

const DEBOUNCE_MS = 350;
const SELECT = "h-10 rounded-lg border border-line bg-surface px-3 text-[14px] text-ink";

type Props = { onSaved: () => void; onCancel: () => void };

/** Enter a purchase; the server previews the split and schedule as you type; save when it looks right. */
export function PlanForm({ onSaved, onCancel }: Props) {
  const providers = useProviders();
  const preview = usePreviewPlan();
  const create = useCreatePlan();
  const [draft, setDraft] = useState<PlanDraft>(() => emptyDraft(todayIso()));

  const provider = providers.data?.find((p) => p.key === draft.provider);
  const input = useMemo(() => toPlanInput(draft, provider), [draft, provider]);
  const inputKey = JSON.stringify(input);
  const { mutate: requestPreview, reset: resetPreview } = preview;

  useEffect(() => {
    if (!input) {
      resetPreview();
      return;
    }
    const timer = setTimeout(() => requestPreview(input), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `inputKey` stands for `input`: re-run only when its contents change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputKey, requestPreview, resetPreview]);

  function set<K extends keyof PlanDraft>(key: K, value: PlanDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    create.reset();
  }

  function save(body: PlanInput) {
    create.mutate(body, { onSuccess: onSaved });
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (input) save(input);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="plan-provider" className="text-xs font-medium text-ink-secondary">
            Provider
          </label>
          <select
            id="plan-provider"
            className={SELECT}
            value={draft.provider}
            onChange={(event) => set("provider", event.target.value as PlanDraft["provider"])}
          >
            {(providers.data ?? []).map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <TextField
          label="What did you buy?"
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
          <ManualFields draft={draft} set={set} />
        )}
      </div>

      {preview.data && input && <PlanPreviewPanel preview={preview.data} />}
      {preview.error && (
        <Banner tone="warning" title="We could not work this out yet">
          {preview.error.message}
        </Banner>
      )}
      {create.error && (
        <Banner tone="danger" title="Not saved">
          {create.error.message}
        </Banner>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={create.isPending}>
          Cancel
        </Button>
        <Button
          type="submit"
          variant="accent"
          disabled={!input || !preview.data || create.isPending}
        >
          {create.isPending ? "Saving…" : "Save plan"}
        </Button>
      </div>
    </form>
  );
}

type ManualProps = {
  draft: PlanDraft;
  set: <K extends keyof PlanDraft>(key: K, value: PlanDraft[K]) => void;
};

/** "Other provider": no rules are applied; the person types what their own checkout showed. */
function ManualFields({ draft, set }: ManualProps) {
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
        <label htmlFor="plan-mode" className="text-xs font-medium text-ink-secondary">
          Your checkout shows
        </label>
        <select
          id="plan-mode"
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
