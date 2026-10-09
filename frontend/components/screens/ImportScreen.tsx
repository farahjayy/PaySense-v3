"use client";

import { PageHeader } from "@/components/ui/PageHeader";

export function ImportScreen() {
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Import" intro="Bring in a bank or e-wallet statement. You review everything before it is saved." />
    </div>
  );
}
