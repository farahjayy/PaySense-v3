"use client";

import { useEffect, useMemo, useState } from "react";

import { PlanFields } from "@/components/plans/PlanFields";
import { PlanPreviewPanel } from "@/components/plans/PlanPreviewPanel";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { useCreatePlan, usePreviewPlan, useProviders, type PlanInput } from "@/lib/api/queries";
import { plural, todayIso } from "@/lib/format";
import { formatRm } from "@/lib/money";
import { emptyDraft, toPlanInput, type PlanDraft } from "@/lib/plans";

const DEBOUNCE_MS = 350;

type Props = {
  onSaved: () => void;
  onCancel: () => void;
  /** Tells the dialog around the form not to close while the plan is being saved. */
  onSavingChange?: (saving: boolean) => void;
};

/** Enter a purchase; the server previews the split and schedule as you type; save when it looks right. */
export function PlanForm({ onSaved, onCancel, onSavingChange }: Props) {
  const providers = useProviders();
  const preview = usePreviewPlan();
  const create = useCreatePlan();
  const [draft, setDraft] = useState<PlanDraft>(() => emptyDraft(todayIso()));

  const provider = providers.data?.find((p) => p.key === draft.provider);
  const input = useMemo(() => toPlanInput(draft, provider), [draft, provider]);
  const inputKey = JSON.stringify(input);
  const { mutate: requestPreview, reset: resetPreview } = preview;
  // The preview on screen belongs to the input it was computed for; once the form moves on, Save
  // waits for the next one so what is saved is always what was shown.
  const previewIsCurrent =
    preview.data !== undefined && JSON.stringify(preview.variables) === inputKey;
  const savingNow = create.isPending;
  useEffect(() => onSavingChange?.(savingNow), [savingNow, onSavingChange]);

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
      <PlanFields draft={draft} set={set} providers={providers.data ?? []} />

      {providers.error && (
        <Banner tone="danger" title="Providers did not load">
          {providers.error.message}
        </Banner>
      )}
      <p role="status" className="text-[13px] text-ink-secondary">
        {!input
          ? "Fill in the purchase to see the schedule."
          : previewIsCurrent && preview.data
            ? `Pay ${formatRm(preview.data.cash_at_purchase_sen)} at checkout, then ${formatRm(
                preview.data.total_payable_sen,
              )} over ${plural(preview.data.installments.length, "instalment")}.`
            : preview.error
              ? ""
              : "Working it out…"}
      </p>
      {preview.data && input && (
        <PlanPreviewPanel preview={preview.data} stale={!previewIsCurrent} />
      )}
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
          disabled={!input || !previewIsCurrent || create.isPending}
        >
          {create.isPending ? "Saving…" : "Save plan"}
        </Button>
      </div>
    </form>
  );
}
