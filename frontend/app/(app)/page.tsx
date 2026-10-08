"use client";

import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import { useAuth } from "@/lib/session";

export default function DashboardPage() {
  const auth = useAuth();
  const name = auth.session?.user.display_name ?? "";
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Hi, {name}</h1>
      <Card className="mt-6">
        <CardTitle>Your dashboard</CardTitle>
        <CardCaption>
          Your balance forecast and BNPL commitments appear here once your transaction history has
          been imported.
        </CardCaption>
      </Card>
    </div>
  );
}
