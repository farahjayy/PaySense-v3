import type { Metadata } from "next";

import { GoogleSignIn } from "@/components/auth/GoogleSignIn";
import { HelloFace } from "@/components/auth/LoginArt";
import { LoginForm } from "@/components/auth/LoginForm";
import { LoginPanel } from "@/components/auth/LoginPanel";
import { LocalTerms } from "@/components/ui/LocalTerms";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  // With Google sign-in on (D-69) it is the main way in; the passphrase form stays for the
  // seeded test and judge accounts, folded away. The pitch panel's one link goes back to /welcome.
  const google = process.env.NEXT_PUBLIC_GOOGLE_SIGNIN === "true";
  return (
    <main className="lg-shell page-enter">
      <LoginPanel />
      <div className="lg-stage">
        <section className="lg-card">
          <HelloFace />
          <h1>Welcome</h1>
          {google ? (
            <>
              <p className="lg-lede">Continue with Google to start.</p>
              <GoogleSignIn />
              <details className="lg-test-account">
                <summary>Use a test account</summary>
                <LoginForm />
              </details>
            </>
          ) : (
            <>
              <p className="lg-lede">Enter your username and passphrase to start.</p>
              <LoginForm />
            </>
          )}
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
