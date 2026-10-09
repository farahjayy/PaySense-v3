"use client";

import { PageHeader } from "@/components/ui/PageHeader";

export function RiskScreen() {
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="BNPL risk check" intro="See how a purchase would affect your finances before you commit to it." />
    </div>
  );
}
