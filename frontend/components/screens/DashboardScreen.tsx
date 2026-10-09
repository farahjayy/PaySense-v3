"use client";

import dynamic from "next/dynamic";

import { BillsDue } from "@/components/forecast/BillsDue";
import { Notices } from "@/components/forecast/Notices";
import { RecentMonths } from "@/components/forecast/RecentMonths";
import { BandBadge } from "@/components/ui/BandBadge";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { ErrorState, LockedState, Skeleton } from "@/components/ui/States";
import { useBills, useForecast, useMonthSummary } from "@/lib/api/queries";
import { formatPercent, plural } from "@/lib/format";
import { notices, OUTLOOK_LINE } from "@/lib/forecast";
import { useAuth } from "@/lib/session";

// Recharts is the heaviest dependency; it loads only once there is a forecast to draw.
const MarginFan = dynamic(
  () => import("@/components/forecast/MarginFan").then((m) => m.MarginFan),
  {
    ssr: false,
    loading: () => <Skeleton lines={6} label="Loading chart" />,
  },
);

export function DashboardScreen() {
  const auth = useAuth();
  const name = auth.session?.user.display_name ?? "";
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title={`Hi, ${name}`} intro="Where your money is heading, and what you owe." />
      <Outlook />
      <div className="grid gap-6 md:grid-cols-2">
        <BillsCard />
        <RecentCard />
      </div>
    </div>
  );
}

function Outlook() {
  const forecast = useForecast();
  if (forecast.isPending) return <Skeleton lines={5} label="Loading your forecast" />;
  if (forecast.isError) {
    return <ErrorState message={forecast.error.message} onRetry={() => forecast.refetch()} />;
  }
  const data = forecast.data;
  if (data.status === "locked" || !data.simulation || !data.band || data.health_score === null) {
    return <LockedState reason={data.lock_reason} monthsOfHistory={data.months_of_history} />;
  }
  const sim = data.simulation;
  return (
    <section aria-labelledby="outlook-heading" className="space-y-4">
      <Card className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-8">
        <ScoreRing score={data.health_score} band={data.band} caption="financial health" />
        <div className="text-center sm:text-left">
          <h2 id="outlook-heading" className="sr-only">
            Your financial health forecast
          </h2>
          <BandBadge band={data.band} large />
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink">
            {OUTLOOK_LINE[data.band]}
          </p>
          <p className="mt-2 text-[13px] text-ink-secondary">
            In {formatPercent(sim.p_shortfall)} of the futures we simulated over the next{" "}
            {plural(sim.months.length, "month")}, your running margin dips below zero at some point.
          </p>
        </div>
      </Card>
      <Notices items={notices(data)} />
      <Card>
        <CardTitle>Your running margin</CardTitle>
        <CardCaption>
          Income minus spending and commitments, added up month by month from the start of this
          month.
        </CardCaption>
        <div className="mt-4">
          <MarginFan simulation={sim} />
        </div>
      </Card>
    </section>
  );
}

function BillsCard() {
  const bills = useBills();
  return (
    <Card>
      <CardTitle>BNPL instalments due</CardTitle>
      <div className="mt-3">
        {bills.isPending ? (
          <Skeleton lines={3} label="Loading instalments" />
        ) : bills.isError ? (
          <ErrorState message={bills.error.message} onRetry={() => bills.refetch()} />
        ) : (
          <BillsDue bills={bills.data} />
        )}
      </div>
    </Card>
  );
}

function RecentCard() {
  const summary = useMonthSummary();
  return (
    <Card>
      <CardTitle>Recent months</CardTitle>
      <CardCaption>What you actually logged.</CardCaption>
      <div className="mt-3">
        {summary.isPending ? (
          <Skeleton lines={4} label="Loading recent months" />
        ) : summary.isError ? (
          <ErrorState message={summary.error.message} onRetry={() => summary.refetch()} />
        ) : (
          <RecentMonths summary={summary.data} />
        )}
      </div>
    </Card>
  );
}
