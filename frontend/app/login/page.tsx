import type { Metadata } from "next";

import { GoogleSignIn } from "@/components/auth/GoogleSignIn";
import { HelloFace } from "@/components/auth/LoginArt";
import { LoginForm } from "@/components/auth/LoginForm";
import { LoginPanel } from "@/components/auth/LoginPanel";
import { LocalTerms } from "@/components/ui/LocalTerms";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  // The pitch panel has nothing to tab to, so the username field is still the first stop for
  // keyboard users even though the panel comes first in the document.
  return (
    <main className="lg-shell">
      <LoginPanel />
      <div className="lg-stage">
        <section className="lg-card">
          <HelloFace />
          <h1>Welcome</h1>
          <p className="lg-lede">Enter your username and passphrase to start.</p>
          <LoginForm />
          <GoogleSignIn />
          <p className="lg-note">
            PaySense gives estimates from your own records. It is not financial advice and not a
            credit decision: you decide, and nothing changes until you confirm it.
          </p>
          <LocalTerms className="lg-terms" />
        </section>
      </div>
    </main>
  );
}
