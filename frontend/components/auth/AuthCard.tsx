"use client";

import { useState, useSyncExternalStore } from "react";

import { GoogleSignIn } from "./GoogleSignIn";
import { HelloFace } from "./LoginArt";
import { LoginForm, type AuthMode } from "./LoginForm";

const COPY: Record<AuthMode, { tab: string; title: string; lede: string }> = {
  signin: {
    tab: "Sign in",
    title: "Welcome back",
    lede: "Sign in to see where your money is heading.",
  },
  signup: {
    tab: "Create account",
    title: "Create your account",
    lede: "Free for students. It takes a minute.",
  },
};

function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** Sign in or create an account, with Google as the other way in when it is switched on. */
export function AuthCard({ google }: { google: boolean }) {
  // the welcome page's "Create your account" links to /login#signup; the server renders sign-in
  const linked = useSyncExternalStore(
    subscribeHash,
    () => window.location.hash === "#signup",
    () => false,
  );
  const [picked, setMode] = useState<AuthMode | null>(null);
  const mode = picked ?? (linked ? "signup" : "signin");
  const copy = COPY[mode];
  return (
    <section className="lg-card">
      <HelloFace />
      <h1>{copy.title}</h1>
      <p className="lg-lede">{copy.lede}</p>
      <div
        role="group"
        aria-label="Sign in or create an account"
        className="lg-tabs"
      >
        {(Object.keys(COPY) as AuthMode[]).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={mode === key}
            className="lg-tab"
            onClick={() => setMode(key)}
          >
            {COPY[key].tab}
          </button>
        ))}
      </div>
      {/* keyed: switching tabs starts a clean form */}
      <LoginForm key={mode} mode={mode} />
      {google && (
        <>
          <p className="lg-or">
            <span>or</span>
          </p>
          <GoogleSignIn />
        </>
      )}
    </section>
  );
}
