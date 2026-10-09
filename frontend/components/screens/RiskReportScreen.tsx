"use client";

import Link from "next/link";

import { RiskResult } from "@/components/risk/RiskResult";
import { Banner } from "@/components/ui/Banner";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { ApiError, useRiskReport } from "@/lib/api/queries";

/** A saved risk check, shown exactly as it was when the plan was added. It never reads the ledger. */
export function RiskReportScreen({ id }: { id: string }) {
  const report = useRiskReport(id);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title="Saved risk check"
        intro="The result you saw when you added this plan. It does not change when your ledger does."
        actions={
          <Link href="/plans" className="text-[13px] font-medium text-accent hover:underline">
            Back to plans
          </Link>
        }
      />
      {report.isPending ? (
        <Skeleton lines={6} label="Loading the saved report" />
      ) : report.isError ? (
        report.error instanceof ApiError && report.error.status === 404 ? (
          <Banner tone="info" title="No such report">
            This report does not exist, or it belongs to another account.
          </Banner>
        ) : (
          <ErrorState message={report.error.message} onRetry={() => report.refetch()} />
        )
      ) : (
        <RiskResult check={report.data} />
      )}
    </div>
  );
}
