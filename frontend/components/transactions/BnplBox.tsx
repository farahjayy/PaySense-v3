import Link from "next/link";

import type { Plan } from "@/lib/api/queries";

/**
 * Shown in place of Edit and Delete on a payment a BNPL plan logged: those rows belong to the
 * plan, so the box says which plan and how far along it is, and links to where it is managed.
 */
export function BnplBox({ plan }: { plan: Plan | undefined }) {
  return (
    <Link
      href="/plans"
      className="block w-full rounded-lg border border-accent/25 bg-accent-bg px-3 py-2 text-[12px] leading-snug text-ink hover:border-accent sm:w-[11.5rem]"
    >
      <span className="block text-[10px] font-semibold uppercase tracking-wide text-accent">
        BNPL plan
      </span>
      {plan && (
        <>
          <span className="block font-medium">
            {plan.provider_label} · {plan.item_name}
          </span>
          <span className="block text-ink-secondary">
            {plan.paid_count} of {plan.num_installments} paid
          </span>
        </>
      )}
      <span className="mt-0.5 block text-accent underline-offset-2 hover:underline">
        Managed in Plans
      </span>
    </Link>
  );
}
