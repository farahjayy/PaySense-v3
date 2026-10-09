/**
 * The Content-Security-Policy for every page. Built per request in `proxy.ts` because scripts are
 * allowed by a fresh nonce, not by `'unsafe-inline'`: injected markup cannot run script, and the
 * only network destinations are this origin and the API (so a script that did run could not send
 * the session token elsewhere).
 *
 * Styles keep `'unsafe-inline'`: server-rendered `style=""` attributes (progress bars, chart
 * sizing) cannot carry a nonce. Style injection is a far smaller risk than script injection, and
 * this is the trade-off Next's own guide describes for apps that set inline styles.
 */

const LOCAL_API = "http://localhost:8000";

export function apiOrigin(raw: string | undefined, isDev: boolean): string {
  const value = raw?.trim();
  if (!value) {
    if (isDev) return LOCAL_API;
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be set to build the Content-Security-Policy.");
  }
  return new URL(value).origin;
}

export type CspOptions = { nonce: string; apiOrigin: string; isDev: boolean };

export function buildCsp({ nonce, apiOrigin: api, isDev }: CspOptions): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src 'self' ${api}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (!isDev) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

/** A fresh, unguessable nonce for one request. */
export function newNonce(): string {
  return Buffer.from(crypto.randomUUID()).toString("base64");
}
