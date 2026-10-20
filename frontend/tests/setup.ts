import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

import { markIntroSeen } from "@/lib/introTour";
import { clearSession } from "@/lib/session";

// Screens are tested without the first-visit tour in the way; its own tests clear this.
beforeEach(() => markIntroSeen());

afterEach(() => {
  cleanup();
  clearSession();
  window.sessionStorage.clear();
  window.localStorage.clear();
});
