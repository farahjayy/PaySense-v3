import type { Metadata } from "next";

import { AuthCard } from "@/components/auth/AuthCard";
import { LoginPanel } from "@/components/auth/LoginPanel";
import { LocalTerms } from "@/components/ui/LocalTerms";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  // Email and password for everyone (D-73); Google beside it when switched on (D-69). Seeded
  // judge and tester accounts sign in with their username in the same field.
  const google = process.env.NEXT_PUBLIC_GOOGLE_SIGNIN === "true";
  return (
    <main className="lg-shell page-enter">
      <LoginPanel />
      <div className="lg-stage">
        <AuthCard google={google} />
        <div className="lg-fine">
          <p className="lg-note">
            PaySense gives estimates from your own records. It is not financial advice and not a
            credit decision: you decide, and nothing changes until you confirm it.
          </p>
          <LocalTerms className="lg-terms" />
        </div>
      </div>
    </main>
  );
}
