import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <main className="grid min-h-screen md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <section
        aria-label="About PaySense"
        className="flex flex-col justify-between bg-accent px-6 py-10 text-white sm:px-10 md:py-14"
      >
        <p className="text-xl font-bold tracking-tight">
          Pay<span className="opacity-70">Sense</span>
        </p>
        <div className="my-10 max-w-md md:my-0">
          <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
            See what a BNPL purchase does to your balance, before you buy.
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-white/80">
            PaySense projects your balance day by day from your own history, bills and instalments,
            then tells you in plain language whether a new plan is safe.
          </p>
        </div>
        <p className="text-xs text-white/70">
          Built for a university final-year project. Uses synthetic persona data only.
        </p>
      </section>
      <section className="flex items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-bold tracking-tight text-ink">Log in</h2>
          <p className="mb-6 mt-1.5 text-[13px] text-ink-secondary">
            Enter your username. There is no password.
          </p>
          <LoginForm />
        </div>
      </section>
    </main>
  );
}
