"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/fields";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { saveSession, useAuth } from "@/lib/session";

export function LoginForm() {
  const router = useRouter();
  const auth = useAuth();
  const [username, setUsername] = useState("");
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
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate aria-busy={isPending}>
      <TextField
        label="Username"
        name="username"
        autoComplete="username"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        maxLength={64}
        value={username}
        onChange={(event) => {
          setUsername(event.target.value);
          if (error) setError(null);
        }}
        hint="The username you were given for this study."
        error={error}
        // read-only, not disabled: a disabled input drops keyboard focus to <body>.
        readOnly={isPending}
      />
      <Button type="submit" variant="accent" disabled={!trimmed || isPending}>
        {isPending ? "Signing in…" : "Continue"}
      </Button>
    </form>
  );
}
