"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";

import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { saveSession, useAuth } from "@/lib/session";

import { ArrowIcon, EyeIcon, EyeOffIcon } from "./LoginArt";

export type AuthMode = "signin" | "signup";

// The server's rule (app/core/passphrase.py, D-49); checked here only to say so before submitting.
const MIN_PASSWORD = 12;

type FieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  describedBy: string;
  invalid: boolean;
  readOnly: boolean;
  type?: string;
  autoComplete: string;
  maxLength: number;
  placeholder?: string;
};

function Field({
  id,
  label,
  onChange,
  describedBy,
  invalid,
  type = "text",
  ...input
}: FieldProps) {
  return (
    <>
      <label htmlFor={id} className="lg-label">
        {label}
      </label>
      <div className={invalid ? "lg-field lg-field-error" : "lg-field"}>
        <input
          id={id}
          className="lg-input"
          type={type}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          // read-only, not disabled: a disabled input drops keyboard focus to <body>.
          {...input}
        />
      </div>
    </>
  );
}

/** Sign in with an email (or a seeded username) and a password, or create an email account. */
export function LoginForm({ mode = "signin" }: { mode?: AuthMode }) {
  const router = useRouter();
  const auth = useAuth();
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const signup = mode === "signup";
  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status === "authenticated") router.replace("/");
  }, [auth.status, router]);

  const trimmed = identifier.trim();
  const ready = signup
    ? name.trim() !== "" &&
      trimmed !== "" &&
      password.trim().length >= MIN_PASSWORD
    : trimmed !== "" && password !== "";
  const describedBy = error ? `${hintId} ${errorId}` : hintId;
  const edit = (set: (value: string) => void) => (value: string) => {
    set(value);
    if (error) setError(null);
  };

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || isPending) return;
    setIsPending(true);
    setError(null);
    try {
      // the password is sent exactly as typed: spaces can be part of it
      const { data, error: apiError } = signup
        ? await api.POST("/api/auth/signup", {
            body: { email: trimmed, password, display_name: name.trim() },
          })
        : await api.POST("/api/auth/login", {
            body: { username: trimmed, passphrase: password },
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

  const common = { describedBy, invalid: !!error, readOnly: isPending };
  return (
    <form
      onSubmit={handleSubmit}
      className="lg-form"
      noValidate
      aria-busy={isPending}
    >
      {signup && (
        <Field
          id={`${id}-name`}
          label="Your name"
          value={name}
          onChange={edit(setName)}
          autoComplete="name"
          maxLength={100}
          placeholder="e.g. Aina"
          {...common}
        />
      )}
      <Field
        id={`${id}-identifier`}
        label={signup ? "Email" : "Email or username"}
        type={signup ? "email" : "text"}
        value={identifier}
        onChange={edit(setIdentifier)}
        autoComplete={signup ? "email" : "username"}
        maxLength={320}
        placeholder="you@example.com"
        {...common}
      />
      <label htmlFor={`${id}-password`} className="lg-label">
        Password
      </label>
      <div className={error ? "lg-field lg-field-error" : "lg-field"}>
        <input
          id={`${id}-password`}
          className="lg-input"
          name="password"
          type={showPassword ? "text" : "password"}
          autoComplete={signup ? "new-password" : "current-password"}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={128}
          value={password}
          onChange={(event) => edit(setPassword)(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          readOnly={isPending}
        />
        <button
          type="button"
          className="lg-eye"
          aria-label="Show password"
          aria-pressed={showPassword}
          onClick={() => setShowPassword((shown) => !shown)}
        >
          {showPassword ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      <p id={hintId} className="lg-hint">
        {signup
          ? `At least ${MIN_PASSWORD} characters. A short sentence is easy to remember.`
          : "Have an invite from the team? Enter its username here."}
      </p>
      {error && (
        <p id={errorId} role="alert" className="lg-error">
          {error}
        </p>
      )}
      <button type="submit" className="lg-go" disabled={!ready || isPending}>
        <span>
          {isPending
            ? signup
              ? "Creating your account…"
              : "Signing in…"
            : signup
              ? "Create account"
              : "Sign in"}
        </span>
        <ArrowIcon />
      </button>
    </form>
  );
}
