"use client";

import { useSyncExternalStore } from "react";

/** The phone layout (below Tailwind's `md`, 768 px), where the assistant panel fills the screen. */
export const PHONE_QUERY = "(max-width: 767px)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => undefined;
  const list = window.matchMedia(PHONE_QUERY);
  list.addEventListener("change", onChange);
  return () => list.removeEventListener("change", onChange);
}

function isPhone(): boolean {
  return (
    typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(PHONE_QUERY).matches
  );
}

/** True on a phone-width screen; false on the server and where matchMedia is missing. */
export function usePhoneLayout(): boolean {
  return useSyncExternalStore(subscribe, isPhone, () => false);
}
