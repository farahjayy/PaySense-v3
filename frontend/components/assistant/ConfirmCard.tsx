"use client";

import Link from "next/link";
import { useState } from "react";

import { PlanPreviewPanel } from "@/components/plans/PlanPreviewPanel";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { useConfirmAction, useDeclineAction } from "@/lib/api/assistant";
import { ApiError } from "@/lib/api/queries";
import {
  actionTitle,
  describeInputs,
  type ActionResult,
  type PendingAction,
} from "@/lib/assistant";
import { formatDate } from "@/lib/format";
import { formatRm } from "@/lib/money";

function PayloadDetails({ action }: { action: PendingAction }) {
  if (action.type === "create_plan" && action.preview) {
    return <PlanPreviewPanel preview={action.preview} />;
  }
  if (action.type === "confirm_import") {
    return (
      <ul className="space-y-1 text-[13px]">
        {action.payload.rows.map((r, i) => (
          <li key={i} className="flex justify-between gap-3">
            <span className="min-w-0 truncate">
              {formatDate(r.date)} · {r.description ?? r.category}
            </span>
            <span className="tabular-nums">
              {r.type === "income" ? "+" : "-"}
              {formatRm(r.amount_sen)}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="space-y-0.5 text-[12px] text-ink-secondary">
      {describeInputs(action.payload as Record<string, unknown>).map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

function Done({ result }: { result: ActionResult }) {
  return (
    <Banner tone="success" title={result.message}>
      {result.plan && (
        <Link
          href={`/risk/${result.plan.check_id}`}
          className="font-medium text-accent underline-offset-2 hover:underline"
        >
          See the saved report
        </Link>
      )}
    </Banner>
  );
}

function failure(error: unknown): string {
  if (error instanceof ApiError && error.status === 410) {
    return "This proposal has expired. Ask again to get a fresh one.";
  }
  if (error instanceof ApiError && error.code === "action_not_pending") {
    return "This proposal has already been used.";
  }
  return error instanceof Error ? error.message : "That did not work.";
}

/**
 * The only way the assistant changes anything (D-48): a card built from the server's stored,
 * validated proposal — never from the model's words — with Confirm and Cancel.
 */
export function ConfirmCard({ action }: { action: PendingAction }) {
  const confirm = useConfirmAction();
  const decline = useDeclineAction();
  const [declined, setDeclined] = useState(false);
  const busy = confirm.isPending || decline.isPending;
  const settled = confirm.isSuccess || declined;
  const headingId = `action-${action.id}`;

  return (
    <section
      aria-labelledby={headingId}
      className="space-y-3 rounded-card border-2 border-accent/40 bg-accent-bg p-3.5"
    >
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-accent">
          Needs your OK
        </p>
        <h3 id={headingId} className="text-[14px] font-semibold text-ink">
          {actionTitle(action.type)}
        </h3>
        <p className="mt-1 text-[13px] text-ink">{action.summary}</p>
      </div>
      <PayloadDetails action={action} />
      {confirm.isSuccess && <Done result={confirm.data} />}
      {declined && <Banner title="Cancelled">Nothing was changed.</Banner>}
      {confirm.isError && (
        <Banner tone="danger" title="Not saved">
          {failure(confirm.error)}
        </Banner>
      )}
      {decline.isError && (
        <Banner tone="danger" title="Not cancelled">
          {failure(decline.error)}
        </Banner>
      )}
      {!settled && !confirm.isError && (
        <div className="flex flex-wrap gap-2">
          <Button variant="accent" disabled={busy} onClick={() => confirm.mutate(action.id)}>
            {confirm.isPending ? "Saving…" : "Confirm"}
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => decline.mutate(action.id, { onSuccess: () => setDeclined(true) })}
          >
            Cancel
          </Button>
        </div>
      )}
    </section>
  );
}
