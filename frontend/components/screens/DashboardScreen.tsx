"use client";

import { PageHeader } from "@/components/ui/PageHeader";
import { useAuth } from "@/lib/session";

export function DashboardScreen() {
  const auth = useAuth();
  const name = auth.session?.user.display_name ?? "";
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title={`Hi, ${name}`} intro="Where your money is heading, and what you owe." />
    </div>
  );
}
