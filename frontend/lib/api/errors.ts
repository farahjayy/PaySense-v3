import type { components } from "./schema";

export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export const NETWORK_ERROR_MESSAGE =
  "Can't reach the server. Check your connection and try again.";
// What browsers and Node throw (as a TypeError) when a request never reaches the server. Any
// other TypeError is a bug in our own code and must not be reported as a connection problem.
const FETCH_FAILURE = /failed to fetch|fetch failed|networkerror|load failed|network request failed/i;
const GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again.";

function isEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("detail" in value)) return false;
  const { detail } = value as { detail: unknown };
  return (
    typeof detail === "object" &&
    detail !== null &&
    typeof (detail as { message?: unknown }).message === "string"
  );
}

/** A user-facing sentence for whatever openapi-fetch gave back as `error`, or a thrown error. */
export function errorMessage(error: unknown, fallback: string = GENERIC_ERROR_MESSAGE): string {
  if (isEnvelope(error)) return error.detail.message;
  if (error instanceof TypeError && FETCH_FAILURE.test(error.message)) return NETWORK_ERROR_MESSAGE;
  return fallback;
}
