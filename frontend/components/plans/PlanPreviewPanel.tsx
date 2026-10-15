import { Banner } from "@/components/ui/Banner";
import type { PlanPreview } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { formatRm } from "@/lib/money";

/**
 * What the server worked out for this purchase, before anything is saved: who pays what, what the
 * borrowing costs, and the instalments. Every figure is the server's (the split, the fee and the
 * total cost); nothing is added up or recalculated here.
 */
export function PlanPreviewPanel({
  preview,
  stale = false,
}: {
  preview: PlanPreview;
  stale?: boolean;
}) {
  const capped = preview.upfront_sen > 0;
  const provider = preview.provider_label;
  // Atome takes the first instalment at checkout: it is part of the instalments, not on top of them.
  const checkoutInstalment = preview.installments.some((i) => i.paid_at_checkout);
  return (
    <div
      className={`space-y-3 rounded-card border border-line bg-surface-2 p-4 ${stale ? "opacity-60" : ""}`}
      aria-busy={stale}
    >
      <dl className="grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-3">
        <Figure
          label="You pay now"
          note={checkoutInstalment ? "includes your first instalment" : "your own money, at checkout"}
          value={formatRm(preview.cash_at_purchase_sen)}
          strong
        />
        <Figure
          label={`${provider} pays the shop`}
          note="you repay it in instalments"
          value={formatRm(preview.financed_sen)}
        />
        <Figure
          label={`All ${preview.num_installments} instalments`}
          note={
            checkoutInstalment
              ? "includes the one you pay now"
              : preview.fee_sen > 0
                ? "fee included"
                : "no fee"
          }
          value={formatRm(preview.total_payable_sen)}
        />
      </dl>
      <div
        role="group"
        aria-label="What this costs"
        className="space-y-1 rounded-lg border border-line bg-surface px-3 py-2.5 text-[13px]"
      >
        <dl className="space-y-1">
          {preview.fee_sen > 0 && (
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-secondary">
                {provider} fee
                <span className="ml-1.5 text-[12px] text-ink-muted">
                  {preview.monthly_fee_rate_pct}% a month for {preview.num_installments} months
                </span>
              </dt>
              <dd className="font-medium tabular-nums">{formatRm(preview.fee_sen)}</dd>
            </div>
          )}
          <div className="flex items-baseline justify-between gap-3">
            <dt className="font-semibold text-ink">Total cost of this purchase</dt>
            <dd className="font-semibold tabular-nums">{formatRm(preview.total_cost_sen)}</dd>
          </div>
        </dl>
        {preview.fee_sen > 0 && (
          <p className="text-[12px] text-ink-secondary">
            {formatRm(preview.fee_sen)} more than the {formatRm(preview.total_price_sen)} price.
          </p>
        )}
      </div>
      {capped && (
        <Banner tone="info" title="Part of this is paid up front">
          Your recorded {provider} limit has {formatRm(preview.remaining_limit_sen ?? 0)} left, and
          the fee counts against it. So {provider} can pay the shop {formatRm(preview.financed_sen)}
          , and you pay the other {formatRm(preview.upfront_sen)} yourself at checkout. (We assume
          the fee counts against the limit; check this against your provider&apos;s checkout.)
        </Banner>
      )}
      {preview.schedule_source === "provider_rule" && !preview.limit_known && (
        <p className="text-[12px] text-ink-secondary">
          Record your {provider} limit below and we will cap what is financed to it.
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

function Figure({
  label,
  note,
  value,
  strong,
}: {
  label: string;
  note: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-0.5">
        <span
          className={`block tabular-nums ${strong ? "text-lg font-semibold text-ink" : "font-medium"}`}
        >
          {value}
        </span>
        <span className="block text-[11px] text-ink-secondary">{note}</span>
      </dd>
    </div>
  );
}
