import createClient, { type Middleware } from "openapi-fetch";

import { clearSession, getSession } from "@/lib/session";
import type { paths } from "./schema";

const LOGIN_PATH = "/api/auth/login";

/** Adds the bearer header, and forgets the session when the server rejects it. */
const sessionMiddleware: Middleware = {
  onRequest({ request }) {
    const session = getSession();
    if (session) request.headers.set("Authorization", `Bearer ${session.token}`);
    return request;
  },
  onResponse({ response, schemaPath }) {
    // A rejected login attempt says nothing about the session we already hold.
    if (response.status === 401 && schemaPath !== LOGIN_PATH) clearSession();
    return response;
  },
};

export function createApiClient(baseUrl: string, fetchImpl?: (request: Request) => Promise<Response>) {
  const client = createClient<paths>({ baseUrl, ...(fetchImpl ? { fetch: fetchImpl } : {}) });
  client.use(sessionMiddleware);
  return client;
}

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

/** The app-wide client. Types come from the backend's OpenAPI document (`npm run gen:api`). */
export const api = createApiClient(API_BASE_URL);
