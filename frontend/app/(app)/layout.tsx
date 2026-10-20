"use client";

import type { ReactNode } from "react";

import { AuthGate } from "@/components/auth/AuthGate";
import { AppShell } from "@/components/layout/AppShell";
import { OnboardingGate } from "@/components/onboarding/Onboarding";
import { useAuth } from "@/lib/session";

function AuthedShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  if (auth.status !== "authenticated") return null; // AuthGate is redirecting or still loading
  return (
    <OnboardingGate>
      <AppShell user={auth.session.user}>{children}</AppShell>
    </OnboardingGate>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <AuthedShell>{children}</AuthedShell>
    </AuthGate>
  );
}
