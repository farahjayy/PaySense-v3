"use client";

import type { ReactNode } from "react";

import { ConsentGate } from "@/components/account/ConsentNotice";
import { AuthGate } from "@/components/auth/AuthGate";
import { AppShell } from "@/components/layout/AppShell";
import { useAuth } from "@/lib/session";

function AuthedShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  if (auth.status !== "authenticated") return null; // AuthGate is redirecting or still loading
  return (
    <AppShell user={auth.session.user}>
      <ConsentGate>{children}</ConsentGate>
    </AppShell>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <AuthedShell>{children}</AuthedShell>
    </AuthGate>
  );
}
