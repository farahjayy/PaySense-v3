import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

import { markIntroSeen, markTourSeen } from "@/lib/introTour";
import { clearSession } from "@/lib/session";

// Screens are tested without the first-visit intro and tour in the way; their own tests clear these.
beforeEach(() => {
  markIntroSeen();
  markTourSeen();
});

afterEach(() => {
  cleanup();
  clearSession();
  window.sessionStorage.clear();
  window.localStorage.clear();
});
