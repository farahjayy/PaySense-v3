import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  // The form comes first in the document (so it is first on a phone and first in tab/reading
  // order); on wide screens the brand panel is moved to the left with `md:order-first`.
  return (
    <main className="grid min-h-dvh md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <section className="flex items-center justify-center px-6 py-10 sm:px-10 md:py-12">
        <div className="w-full max-w-sm">
          <p className="mb-8 text-xl font-bold tracking-tight text-ink md:hidden">
            Pay<span className="text-accent">Sense</span>
          </p>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Log in</h1>
          <p className="mb-6 mt-1.5 text-[13px] text-ink-secondary">
            Enter your username. There is no password.
          </p>
          <LoginForm />
        </div>
      </section>
      <section
        aria-label="About PaySense"
        className="flex flex-col justify-between gap-10 bg-accent px-6 py-10 text-white sm:px-10 md:order-first md:py-14"
      >
        <p className="hidden text-xl font-bold tracking-tight md:block">
          Pay<span className="opacity-70">Sense</span>
        </p>
        <div className="max-w-md">
          <h2 className="text-2xl font-bold leading-tight tracking-tight sm:text-3xl md:text-4xl">
            See what a BNPL purchase does to your monthly budget, before you buy.
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-white/90">
            PaySense projects your monthly margin from your own history, bills and instalments,
            then tells you in plain language whether a new plan is safe.
          </p>
        </div>
        <p className="text-xs text-white/90">
          Built for a university final-year project. Uses synthetic persona data only.
        </p>
      </section>
    </main>
  );
}
