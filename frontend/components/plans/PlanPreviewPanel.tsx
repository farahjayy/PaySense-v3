import { Banner } from "@/components/ui/Banner";
import type { PlanPreview } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { formatRm } from "@/lib/money";

/**
 * What the server worked out for this purchase, before anything is saved. The split between what
 * the provider finances and what is paid at checkout is the server's, never recalculated here.
 */
export function PlanPreviewPanel({ preview }: { preview: PlanPreview }) {
  const capped = preview.upfront_sen > 0;
  return (
    <div className="space-y-3 rounded-card border border-line bg-surface-2 p-4" aria-live="polite">
      <dl className="grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-3">
        <Figure label="Pay at checkout" value={formatRm(preview.cash_at_purchase_sen)} strong />
        <Figure label="Financed" value={formatRm(preview.financed_sen)} />
        <Figure label="Total you will repay" value={formatRm(preview.total_payable_sen)} />
      </dl>
      {capped && (
        <Banner tone="info" title="Part of this is paid up front">
          Your recorded {preview.provider_label} limit has{" "}
          {formatRm(preview.remaining_limit_sen ?? 0)} left, so the provider finances{" "}
          {formatRm(preview.financed_sen)} and the remaining {formatRm(preview.upfront_sen)} is paid
          at checkout.
        </Banner>
      )}
      {preview.schedule_source === "provider_rule" && !preview.limit_known && (
        <p className="text-[12px] text-ink-secondary">
          Record your {preview.provider_label} limit below and we will cap what is financed to it.
        </p>
      )}
      <ol className="divide-y divide-line rounded-lg border border-line bg-surface text-[13px]">
        {preview.installments.map((i) => (
          <li key={i.seq} className="flex items-center justify-between px-3 py-2">
            <span>
              {i.seq}. {formatDate(i.due_date)}
              {i.paid_at_checkout && (
                <span className="ml-2 text-[12px] text-ink-secondary">at checkout</span>
              )}
            </span>
            <span className="font-semibold tabular-nums">{formatRm(i.amount_sen)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd
        className={`mt-0.5 tabular-nums ${strong ? "text-lg font-semibold text-ink" : "font-medium"}`}
      >
        {value}
      </dd>
    </div>
  );
}
