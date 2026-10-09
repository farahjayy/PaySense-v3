"use client";

import { PageHeader } from "@/components/ui/PageHeader";

export function TransactionsScreen() {
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Transactions" intro="Everything you have logged or imported, newest first." />
    </div>
  );
}
