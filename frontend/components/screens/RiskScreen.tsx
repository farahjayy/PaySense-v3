"use client";

import { Banner } from "@/components/ui/Banner";
import { PageHeader } from "@/components/ui/PageHeader";

export function RiskScreen() {
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        title="BNPL risk check"
        intro="See how a purchase would affect your finances before you commit to it."
      />
      <Banner tone="info" title="Not available yet">
        The risk check is still being finished. In the meantime you can add a plan under BNPL plans
        and watch how your forecast changes.
      </Banner>
    </div>
  );
}
