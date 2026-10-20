"use client";

import { useRef, useState } from "react";

const SEEN_KEY = "paysense.intro.seen";

/** Whether this browser has already seen the intro tour. Blocked storage counts as unseen. */
export function introSeen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function markIntroSeen(): void {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // not kept: the intro shows again on the next visit, never twice in one
  }
}

/**
 * Replaying the intro from the profile menu. The first showing is the onboarding gate's job
 * (components/onboarding/Onboarding.tsx).
 */
export function useIntroTour() {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLElement | null>(null); // focus goes back here when the replay closes
  return {
    open,
    show: () => {
      opener.current = document.activeElement as HTMLElement | null;
      setOpen(true);
    },
    close: () => {
      setOpen(false);
      opener.current?.focus();
      opener.current = null;
    },
  };
}
