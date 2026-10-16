import type { Metadata } from "next";

import { HelloFace } from "@/components/auth/LoginArt";
import { LoginForm } from "@/components/auth/LoginForm";
import { LoginPanel } from "@/components/auth/LoginPanel";

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
          <p className="lg-lede">Enter your username to start. There is no password.</p>
          <LoginForm />
        </section>
      </div>
    </main>
  );
}
