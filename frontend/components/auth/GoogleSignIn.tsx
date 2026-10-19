"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { API_BASE_URL, api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { saveSession } from "@/lib/session";

const HANDOFF = "#google=";

// What the API's callback puts in ?error= (ADR D-69).
const CALLBACK_ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled.",
  state: "That sign-in link expired. Please try again.",
  too_many: "Too many failed sign-ins. Try again in a few minutes.",
};
const GENERIC = "Google sign-in failed. Please try again.";

function callbackError(): string | null {
  const reason = new URLSearchParams(window.location.search).get("error");
  return reason === null ? null : (CALLBACK_ERRORS[reason] ?? GENERIC);
}

const subscribeNothing = () => () => {};

/**
 * "Continue with Google", and the end of that flow: the API's callback sends the browser back
 * here with a one-time code in the fragment, which is exchanged for the same session as the
 * passphrase login. Off unless NEXT_PUBLIC_GOOGLE_SIGNIN is "true".
 */
export function GoogleSignIn() {
  const router = useRouter();
  const [exchangeError, setExchangeError] = useState<string | null>(null);
  // read after hydration only: the server cannot see the URL's query
  const redirectError = useSyncExternalStore(subscribeNothing, callbackError, () => null);
  const error = exchangeError ?? redirectError;
  const enabled = process.env.NEXT_PUBLIC_GOOGLE_SIGNIN === "true";

  useEffect(() => {
    const { hash, pathname, search } = window.location;
    if (!enabled || !hash.startsWith(HANDOFF)) return;
    // Forget the code before using it: it works once, and must not stay in history.
    const code = hash.slice(HANDOFF.length);
    window.history.replaceState(null, "", pathname + search);
    api
      .POST("/api/auth/google/exchange", { body: { code } })
      .then(({ data, error: apiError }) => {
        if (!data) {
          setExchangeError(errorMessage(apiError, GENERIC));
          return;
        }
        saveSession({
          token: data.access_token,
          expiresAt: Date.now() + data.expires_in * 1000,
          user: data.user,
        });
        router.replace("/");
      })
      .catch((thrown: unknown) => setExchangeError(errorMessage(thrown, GENERIC)));
  }, [enabled, router]);

  if (!enabled) return null;
  return (
    <div className="lg-google-block">
      {/* A real navigation, not fetch: the flow runs through Google's pages and the API's cookie. */}
      <a className="lg-google" href={`${API_BASE_URL}/api/auth/google`}>
        <GoogleMark />
        <span>Continue with Google</span>
      </a>
      {error && (
        <p role="alert" className="lg-error">
          {error}
        </p>
      )}
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.1C12.5 13.6 17.8 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.4 5.7c4.3-4 6.9-9.9 6.9-17.1z" />
      <path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.1C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.3-8.5 2.3-6.2 0-11.5-4.1-13.4-9.9l-7.9 6.1C6.6 42.6 14.6 48 24 48z" />
    </svg>
  );
}
