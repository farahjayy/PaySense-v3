"use client";

import { useRef, useState, useSyncExternalStore } from "react";

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
    // not kept: the tour shows again on the next visit, never twice in one
  }
}

const subscribeNothing = () => () => {};

/**
 * The tour opens by itself once per browser and again whenever the person asks for it. Read on
 * the server as "seen", so the tour never flashes in a server render.
 */
export function useIntroTour() {
  const seen = useSyncExternalStore(subscribeNothing, introSeen, () => true);
  const [closedNow, setClosedNow] = useState(false); // covers a browser that will not store it
  const [replaying, setReplaying] = useState(false);
  const opener = useRef<HTMLElement | null>(null); // focus goes back here when a replay closes
  return {
    open: replaying || (!seen && !closedNow),
    show: () => {
      opener.current = document.activeElement as HTMLElement | null;
      setReplaying(true);
    },
    close: () => {
      markIntroSeen();
      setClosedNow(true);
      setReplaying(false);
      opener.current?.focus();
      opener.current = null;
    },
  };
}
