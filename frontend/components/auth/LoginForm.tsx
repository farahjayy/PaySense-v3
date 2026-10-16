"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";

import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { saveSession, useAuth } from "@/lib/session";

import { ArrowIcon, EyeIcon, EyeOffIcon } from "./LoginArt";

// Who a tester messages when they have lost their username.
const SUPPORT_CONTACT = "Farah";

export function LoginForm() {
  const router = useRouter();
  const auth = useAuth();
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const [username, setUsername] = useState("");
  const [isHidden, setIsHidden] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status === "authenticated") router.replace("/");
  }, [auth.status, router]);

  const trimmed = username.trim();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!trimmed || isPending) return;
    setIsPending(true);
    setError(null);
    try {
      const { data, error: apiError } = await api.POST("/api/auth/login", {
        body: { username: trimmed },
      });
      if (!data) {
        setError(errorMessage(apiError));
        return;
      }
      // If sessionStorage is blocked the session is kept in memory: login still works for this
      // tab, it just will not survive a reload.
      saveSession({
        token: data.access_token,
        expiresAt: Date.now() + data.expires_in * 1000,
        user: data.user,
      });
      router.replace("/");
    } catch (thrown: unknown) {
      setError(errorMessage(thrown));
    } finally {
      setIsPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="lg-form" noValidate aria-busy={isPending}>
      <label htmlFor={inputId} className="lg-label">
        Username
      </label>
      <div className={error ? "lg-field lg-field-error" : "lg-field"}>
        <input
          id={inputId}
          className="lg-input"
          name="username"
          type={isHidden ? "password" : "text"}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={64}
          placeholder="e.g. amir"
          value={username}
          onChange={(event) => {
            setUsername(event.target.value);
            if (error) setError(null);
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          // read-only, not disabled: a disabled input drops keyboard focus to <body>.
          readOnly={isPending}
        />
        {/* The username is the only credential, so a tester can hide it before a screenshot. */}
        <button
          type="button"
          className="lg-eye"
          aria-label="Hide text"
          aria-pressed={isHidden}
          onClick={() => setIsHidden((hidden) => !hidden)}
        >
          {isHidden ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      <p id={hintId} className="lg-hint">
        Use the username from your invite. Lost it? Message <strong>{SUPPORT_CONTACT}</strong>.
      </p>
      {error && (
        <p id={errorId} role="alert" className="lg-error">
          {error}
        </p>
      )}
      <button type="submit" className="lg-go" disabled={!trimmed || isPending}>
        <span>{isPending ? "Signing in…" : "Continue"}</span>
        <ArrowIcon />
      </button>
    </form>
  );
}
