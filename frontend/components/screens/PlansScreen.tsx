"use client";

import { useState } from "react";

import { PlanForm } from "@/components/plans/PlanForm";
import { ProviderLimits } from "@/components/plans/ProviderLimits";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Dialog } from "@/components/ui/Dialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import {
  useDeletePlan,
  usePayInstalment,
  usePayInstalments,
  usePlans,
  type Plan,
} from "@/lib/api/queries";
import { formatDate, plural } from "@/lib/format";
import { formatRm } from "@/lib/money";

const STATUS = {
  active: { label: "Active", cls: "border-accent/30 bg-accent-bg text-accent" },
  completed: { label: "Completed", cls: "border-success/30 bg-success-bg text-success" },
  overdue: { label: "Overdue", cls: "border-danger/30 bg-danger-bg text-danger" },
} as const;

export function PlansScreen() {
  const plans = usePlans();
  const [adding, setAdding] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Plan | null>(null);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title="BNPL plans"
        intro="The instalment plans you have committed to, and what is still to pay."
        actions={
          <Button variant="accent" onClick={() => setAdding(true)}>
            Add a plan
          </Button>
        }
      />
      {plans.isPending ? (
        <Skeleton lines={5} label="Loading plans" />
      ) : plans.isError ? (
        <ErrorState message={plans.error.message} onRetry={() => plans.refetch()} />
      ) : plans.data.length === 0 ? (
        <EmptyState
          title="No plans yet"
          action={<Button onClick={() => setAdding(true)}>Add a plan</Button>}
        >
          Add a purchase you are paying in instalments, or run a BNPL risk check before you commit
          to one.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {plans.data.map((plan) => (
            <li key={plan.id}>
              <PlanCard plan={plan} onDelete={() => setDeleting(plan)} />
            </li>
          ))}
        </ul>
      )}
      <ProviderLimits />

      <Dialog
        open={adding}
        title="Add a BNPL plan"
        onClose={() => setAdding(false)}
        dismissible={!creating}
      >
        {adding && (
          <PlanForm
            onSaved={() => setAdding(false)}
            onCancel={() => setAdding(false)}
            onSavingChange={setCreating}
          />
        )}
      </Dialog>
      <DeleteDialog plan={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}

function PlanCard({ plan, onDelete }: { plan: Plan; onDelete: () => void }) {
  const pay = usePayInstalment();
  const payMany = usePayInstalments();
  const [open, setOpen] = useState(false);
  const status = STATUS[plan.status];
  const due = plan.installments.filter((i) => !i.is_paid);
  const error = pay.error?.message ?? payMany.error?.message ?? null;
  // One request at a time per plan: single and bulk payments must not overlap.
  const busy = pay.isPending || payMany.isPending;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold text-ink">{plan.item_name}</h2>
          <p className="mt-0.5 text-[12px] text-ink-secondary">
            {plan.provider_label} · {plural(plan.num_installments, "instalment")} of{" "}
            {formatRm(plan.installment_amount_sen)} · bought {formatDate(plan.purchase_date)}
          </p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${status.cls}`}>
          {status.label}
        </span>
      </div>
      <p className="mt-3 text-[13px] text-ink-secondary">
        {plan.paid_count} of {plan.num_installments} paid
        {plan.next_due_date && ` · next due ${formatDate(plan.next_due_date)}`}
        {plan.upfront_sen > 0 && ` · ${formatRm(plan.upfront_sen)} was paid at checkout`}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide instalments" : "Show instalments"}
        </Button>
        {due.length > 1 && (
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => payMany.mutate({ planId: plan.id, seqs: due.map((i) => i.seq) })}
          >
            Mark all {due.length} as paid
          </Button>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={onDelete}
          aria-label={`Delete plan, ${plan.item_name}`}
        >
          Delete plan
        </Button>
      </div>
      {error && (
        <Banner tone="danger" className="mt-3" title="Not updated">
          {error}
        </Banner>
      )}
      {open && (
        <ol className="mt-3 divide-y divide-line rounded-lg border border-line text-[13px]">
          {plan.installments.map((i) => (
            <li key={i.seq} className="flex items-center justify-between gap-3 px-3 py-2">
              <span>
                {i.seq}. {formatDate(i.due_date)}
                {i.is_paid && i.paid_date && (
                  <span className="ml-2 text-[12px] text-success">
                    paid {formatDate(i.paid_date)}
                  </span>
                )}
              </span>
              <span className="flex items-center gap-3">
                <span className="font-semibold tabular-nums">{formatRm(i.amount_sen)}</span>
                {!i.is_paid && (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => pay.mutate({ planId: plan.id, seq: i.seq })}
                    aria-label={`Mark paid, instalment ${i.seq} of ${plan.item_name}`}
                  >
                    Mark paid
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function DeleteDialog({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const remove = useDeletePlan();
  const [keepPayments, setKeepPayments] = useState(true);

  function close() {
    remove.reset();
    setKeepPayments(true); // never carry an unticked box over to the next plan
    onClose();
  }

  return (
    <Dialog
      open={plan !== null}
      title="Delete this plan?"
      onClose={close}
      dismissible={!remove.isPending}
    >
      {plan && (
        <div className="space-y-4">
          <p className="text-[13px] text-ink-secondary">
            {plan.item_name} ({plan.provider_label}). The remaining instalments disappear from your
            bills and forecast.
          </p>
          <label className="flex items-start gap-2 text-[13px]">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]"
              checked={keepPayments}
              onChange={(event) => setKeepPayments(event.target.checked)}
            />
            <span>
              Keep the payments already logged as ordinary transactions
              <span className="block text-[12px] text-ink-secondary">
                Untick to delete them from your history too.
              </span>
            </span>
          </label>
          {remove.error && (
            <Banner tone="danger" title="Not deleted">
              {remove.error.message}
            </Banner>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close} disabled={remove.isPending}>
              Keep the plan
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate({ id: plan.id, keepPayments }, { onSuccess: close })}
            >
              {remove.isPending ? "Deleting…" : "Delete plan"}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
