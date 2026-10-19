import createClient, { type Middleware } from "openapi-fetch";

import { clearSession, getSession } from "@/lib/session";
import type { paths } from "./schema";

const LOGIN_PATH = "/api/auth/login";
const API_URL_VARIABLE = "NEXT_PUBLIC_API_BASE_URL";
const LOCAL_API_URL = "http://localhost:8000";

/**
 * The API origin. Outside production a missing variable falls back to the local backend; in a
 * production build it is an error, because the value is inlined at build time and a bundle that
 * silently calls the visitor's own localhost would report every login as "can't reach the server".
 */
export function resolveApiBaseUrl(value: string | undefined, nodeEnv: string | undefined): string {
  const configured = value?.trim();
  if (!configured) {
    if (nodeEnv === "production") {
      throw new Error(`${API_URL_VARIABLE} must be set for a production build (see env_setup.md).`);
    }
    return LOCAL_API_URL;
  }
  return configured.replace(/\/+$/, "");
}

/** Adds the bearer header, and forgets the session when the server rejects *that* session. */
function createSessionMiddleware(): Middleware {
  // Which token each in-flight request carried, so a late 401 for an old token cannot wipe a
  // session created after the request was sent.
  const sentWith = new Map<string, string>();
  return {
    onRequest({ request, id }) {
      const session = getSession();
      if (session) {
        request.headers.set("Authorization", `Bearer ${session.token}`);
        sentWith.set(id, session.token);
      }
      return request;
    },
    onResponse({ response, schemaPath, id }) {
      const token = sentWith.get(id);
      sentWith.delete(id);
      // A rejected login attempt says nothing about the session we already hold.
      if (response.status === 401 && schemaPath !== LOGIN_PATH && getSession()?.token === token) {
        clearSession();
      }
      return response;
    },
    onError({ id }) {
      sentWith.delete(id);
    },
  };
}

export function createApiClient(
  baseUrl: string,
  fetchImpl?: (request: Request) => Promise<Response>,
) {
  const client = createClient<paths>({ baseUrl, ...(fetchImpl ? { fetch: fetchImpl } : {}) });
  client.use(createSessionMiddleware());
  return client;
}

export const API_BASE_URL = resolveApiBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL,
  process.env.NODE_ENV,
);

/** The app-wide client. Types come from the backend's OpenAPI document (`pnpm gen:api`). */
export const api = createApiClient(API_BASE_URL);
