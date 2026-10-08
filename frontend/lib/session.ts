"use client";

import { useSyncExternalStore } from "react";
import { z } from "zod";

/**
 * The login session (ADR D-03): a bearer credential plus the user, kept in sessionStorage so it
 * dies with the tab. Reads never throw — storage can be blocked — and never have side effects, so
 * they are safe inside useSyncExternalStore snapshots.
 */
const SessionSchema = z.object({
  token: z.string().min(1),
  expiresAt: z.number(),
  user: z.object({
    id: z.string(),
    username: z.string(),
    display_name: z.string(),
    persona: z.enum(["frequent_bnpl", "budget_conscious", "irregular_income"]).nullable(),
  }),
});

export type Session = z.infer<typeof SessionSchema>;

const STORAGE_KEY = "paysense.session";
const listeners = new Set<() => void>();
let cache: { raw: string | null; value: Session | null } = { raw: null, value: null };

function readRaw(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function parse(raw: string | null): Session | null {
  if (raw === null) return null;
  try {
    const result = SessionSchema.safeParse(JSON.parse(raw));
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

/** The stored session, or null if absent, malformed or expired. Stable between unchanged reads. */
export function getSession(now: number = Date.now()): Session | null {
  const raw = readRaw();
  if (raw !== cache.raw) cache = { raw, value: parse(raw) };
  const { value } = cache;
  return value !== null && value.expiresAt > now ? value : null;
}

export function saveSession(session: Session): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* storage blocked: the session simply will not survive a reload */
  }
  notify();
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
  notify();
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export type AuthState =
  | { status: "loading"; session: null }
  | { status: "anonymous"; session: null }
  | { status: "authenticated"; session: Session };

const subscribeNothing = () => () => {};

/**
 * Where the visitor stands. "loading" covers the server render and the hydration pass, when
 * sessionStorage cannot be known yet — callers must not redirect while loading.
 */
export function useAuth(): AuthState {
  const hydrated = useSyncExternalStore(subscribeNothing, () => true, () => false);
  const session = useSyncExternalStore(subscribeSession, () => getSession(), () => null);
  if (!hydrated) return { status: "loading", session: null };
  return session ? { status: "authenticated", session } : { status: "anonymous", session: null };
}
