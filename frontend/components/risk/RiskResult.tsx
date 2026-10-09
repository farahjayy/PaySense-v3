"use client";

import dynamic from "next/dynamic";
import type { ReactNode } from "react";

import { Notices } from "@/components/forecast/Notices";
import { PlanPreviewPanel } from "@/components/plans/PlanPreviewPanel";
import { RepaymentCard } from "@/components/risk/RepaymentCard";
import { SuggestionCard } from "@/components/risk/SuggestionCard";
import { BandBadge } from "@/components/ui/BandBadge";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { LockedState, Skeleton } from "@/components/ui/States";
import type { PlanInput, RiskCheck } from "@/lib/api/queries";
import { BAND_COPY, formatPercent } from "@/lib/format";
import { riskNotices } from "@/lib/risk";

const WithWithoutChart = dynamic(
  () => import("@/components/risk/WithWithoutChart").then((m) => m.WithWithoutChart),
  { ssr: false, loading: () => <Skeleton lines={6} label="Loading chart" /> },
);

type Props = {
  check: RiskCheck;
  onTrySuggestion?: (request: PlanInput) => void;
  busy?: boolean;
  /** Dimmed while the form has moved on from what was checked. */
  stale?: boolean;
  footer?: ReactNode;
};

export function RiskResult({ check, onTrySuggestion, busy, stale = false, footer }: Props) {
  if (check.status !== "ok" || check.probability === null || !check.band || check.score === null) {
    return <LockedState reason={check.lock_reason} monthsOfHistory={check.months_of_history} />;
  }
  const copy = BAND_COPY[check.band];
  return (
    <div className={`space-y-4 ${stale ? "opacity-60" : ""}`} aria-busy={stale}>
      <Card className="flex flex-col items-center gap-5 sm:flex-row sm:gap-8">
        <ScoreRing score={check.score} band={check.band} caption="out of 100" />
        <div className="text-center sm:text-left">
          <BandBadge band={check.band} large />
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink">{copy.line}</p>
          <p className="mt-2 text-[13px] text-ink-secondary">
            Estimated chance of running short: {formatPercent(check.probability)}.
            {check.simulated_probability !== null && (
              <>
                {" "}
                A direct simulation of this purchase gives{" "}
                {formatPercent(check.simulated_probability)}.
              </>
            )}
          </p>
        </div>
      </Card>
      <Notices items={riskNotices(check)} />
      <PlanPreviewPanel preview={check.plan} />
      <Card>
        <CardTitle>Why</CardTitle>
        {check.factors.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[14px] leading-relaxed text-ink">
            {check.factors.map((f) => (
              <li key={f.feature}>{f.text}</li>
            ))}
          </ul>
        ) : (
          <CardCaption>
            Nothing in your numbers stands out as pushing the risk up. The result reflects your
            overall pattern.
          </CardCaption>
        )}
      </Card>
      {check.suggestion && (
        <SuggestionCard suggestion={check.suggestion} onTry={onTrySuggestion} busy={busy} />
      )}
      {check.with_plan_curve && check.without_curve && (
        <Card>
          <CardTitle>Your running margin, with and without this purchase</CardTitle>
          <div className="mt-4">
            <WithWithoutChart withPlan={check.with_plan_curve} without={check.without_curve} />
          </div>
        </Card>
      )}
      <RepaymentCard repayment={check.repayment} />
      {footer}
    </div>
  );
}
