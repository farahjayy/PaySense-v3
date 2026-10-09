import { Banner } from "@/components/ui/Banner";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import type { RiskCheck } from "@/lib/api/queries";
import { plural } from "@/lib/format";
import { formatRm } from "@/lib/money";

const TONE = { none: "success", watch: "warning", warning: "danger" } as const;

/**
 * Repayment history, deliberately separate from the score: it is a rule applied to the student's
 * own instalments, not an input to the model.
 */
export function RepaymentCard({ repayment }: { repayment: RiskCheck["repayment"] }) {
  return (
    <Card>
      <CardTitle>Your repayment history</CardTitle>
      <CardCaption>Shown beside the result, never part of it.</CardCaption>
      <Banner tone={TONE[repayment.level]} className="mt-3">
        {repayment.reason}
        {repayment.overdue_count > 0 && (
          <span className="mt-1 block">
            {plural(repayment.overdue_count, "instalment")} overdue,{" "}
            {formatRm(repayment.overdue_sen)} in all.
          </span>
        )}
      </Banner>
    </Card>
  );
}
