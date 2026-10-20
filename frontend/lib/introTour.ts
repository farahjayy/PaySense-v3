"use client";

import { useRef, useState } from "react";

const SEEN_KEY = "paysense.intro.seen";
const TOUR_KEY = "paysense.tour.seen";

// Blocked storage counts as unseen; a mark that cannot be kept shows it again next visit, never twice in one.
function seen(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function mark(key: string): void {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // not kept
  }
}

/** Whether this browser has already seen the intro slides. */
export const introSeen = () => seen(SEEN_KEY);
export const markIntroSeen = () => mark(SEEN_KEY);

/** Whether this browser has already had the guided tour of the app itself (components/onboarding/Tour.tsx). */
export const tourSeen = () => seen(TOUR_KEY);
export const markTourSeen = () => mark(TOUR_KEY);

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
