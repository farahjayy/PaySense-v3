"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { PlanFields } from "@/components/plans/PlanFields";
import { RiskResult } from "@/components/risk/RiskResult";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  useConfirmRisk,
  useProviders,
  useRiskCheck,
  type PlanInput,
  type RiskCheck,
} from "@/lib/api/queries";
import { todayIso } from "@/lib/format";
import { emptyDraft, toPlanInput, type PlanDraft } from "@/lib/plans";
import { draftFromInput } from "@/lib/risk";

export function RiskScreen() {
  const providers = useProviders();
  const check = useRiskCheck();
  const confirm = useConfirmRisk();
  const [draft, setDraft] = useState<PlanDraft>(() => emptyDraft(todayIso()));
  const [checked, setChecked] = useState<{
    input: PlanInput;
    result: RiskCheck;
  } | null>(null);

  const provider = providers.data?.find((p) => p.key === draft.provider);
  const input = useMemo(() => toPlanInput(draft, provider), [draft, provider]);
  const stale =
    checked !== null && JSON.stringify(checked.input) !== JSON.stringify(input);

  function set<K extends keyof PlanDraft>(key: K, value: PlanDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function run(body: PlanInput) {
    confirm.reset();
    check.mutate(body, {
      onSuccess: (result) => setChecked({ input: body, result }),
    });
  }

  function trySuggestion(request: PlanInput) {
    // Through the form's own shape: the server sends explicit nulls for fields a plan does not
    // use, and the result must count as current only when it matches what the form would send.
    const next = draftFromInput(request, todayIso());
    const body = toPlanInput(
      next,
      providers.data?.find((p) => p.key === next.provider),
    );
    setDraft(next);
    if (body) run(body);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="BNPL risk check"
        intro="See how a purchase would affect your finances before you commit to it. Nothing is saved until you choose to add it as a plan."
      />
      {confirm.data ? (
        <Added check={confirm.data.check_id} />
      ) : (
        <>
          <form
            className="space-y-4 rounded-card border border-line bg-surface p-4 sm:p-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (input) run(input);
            }}
          >
            <PlanFields
              draft={draft}
              set={set}
              providers={providers.data ?? []}
              idPrefix="risk"
            />
            {providers.error && (
              <Banner tone="danger" title="Providers did not load">
                {providers.error.message}
              </Banner>
            )}
            {check.error && (
              <Banner tone="danger" title="The check did not run">
                {check.error.message}
              </Banner>
            )}
            <div className="flex items-center justify-between gap-3">
              <p className="text-[12px] text-ink-secondary">
                {input ? "" : "Fill in the purchase to check it."}
              </p>
              <Button
                type="submit"
                variant="accent"
                disabled={!input || check.isPending}
              >
                {check.isPending
                  ? "Checking…"
                  : checked
                    ? "Check again"
                    : "Check this purchase"}
              </Button>
            </div>
          </form>
          {checked && (
            <section aria-label="Result" className="space-y-4">
              {stale && (
                <Banner tone="info" title="You have changed the purchase">
                  This result is for what you entered before. Check again to
                  update it.
                </Banner>
              )}
              <RiskResult
                check={checked.result}
                request={checked.input}
                stale={stale}
                busy={check.isPending}
                onTrySuggestion={trySuggestion}
                footer={
                  checked.result.status === "ok" && (
                    <GoAhead
                      disabled={stale || confirm.isPending}
                      pending={confirm.isPending}
                      error={confirm.error?.message ?? null}
                      onConfirm={() => confirm.mutate(checked.input)}
                    />
                  )
                }
              />
            </section>
          )}
        </>
      )}
    </div>
  );
}

type GoAheadProps = {
  disabled: boolean;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
};

function GoAhead({ disabled, pending, error, onConfirm }: GoAheadProps) {
  return (
    <div className="space-y-3 rounded-card border border-line bg-surface p-4 sm:p-5">
      <h2 className="text-sm font-semibold text-ink">Going ahead?</h2>
      <p className="text-[13px] leading-relaxed text-ink-secondary">
        Adding it saves this result as a report and creates the plan, so it
        shows up in your bills and forecast. You can still change your mind
        first.
      </p>
      {error && (
        <Banner tone="danger" title="Not added">
          {error}
        </Banner>
      )}
      <Button variant="primary" disabled={disabled} onClick={onConfirm}>
        {pending ? "Adding…" : "Add this as a plan"}
      </Button>
    </div>
  );
}

function Added({ check }: { check: string }) {
  return (
    <div className="space-y-4">
      <Banner tone="success" title="Plan added">
        The plan is in your bills and your forecast has been refreshed. This
        result is saved as a report.
      </Banner>
      <div className="flex flex-wrap gap-2">
        <Link
          href={`/risk/${check}`}
          className="inline-flex h-10 items-center rounded-lg bg-ink px-4 text-[13px] font-semibold text-white hover:bg-ink/85"
        >
          See the saved report
        </Link>
        <Link
          href="/plans"
          className="inline-flex h-10 items-center rounded-lg border border-line bg-surface px-4 text-[13px] font-semibold text-ink hover:bg-surface-2"
        >
          Go to my plans
        </Link>
      </div>
    </div>
  );
}
