import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

// A machine whose Playwright browsers do not match this version (e.g. a pre-provisioned cloud
// container) points PW_CHROMIUM_PATH at its own Chromium instead of downloading one.
const launchOptions = process.env.PW_CHROMIUM_PATH
  ? { executablePath: process.env.PW_CHROMIUM_PATH }
  : {};

/**
 * The real-model journey (WP1): the production build against an API that is ALREADY running on
 * the real database with the served risk model (`cd backend && uv run uvicorn app.main:app
 * --port 8000`). A throwaway account is created before and deleted after (cascade), so the run
 * leaves nothing behind.
 *
 *   cd frontend && npx playwright test -c playwright.real.config.ts
 */
const FRONTEND_URL = "http://localhost:3000"; // must be in the API's CORS_ORIGINS
export const REAL_API_URL = process.env.REAL_API_URL ?? "http://localhost:8000";
export const ACCOUNT_FILE = path.resolve(__dirname, "../data/private/e2e-real-account.json");
const uvBin = path.join(os.homedir(), ".local", "bin");
process.env.PATH = `${uvBin}${path.delimiter}${process.env.PATH ?? ""}`;

export default defineConfig({
  testDir: "./tests/e2e-real",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  globalSetup: "./tests/e2e-real/setup.ts",
  globalTeardown: "./tests/e2e-real/teardown.ts",
  use: { baseURL: FRONTEND_URL, trace: "retain-on-failure", launchOptions },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "npm run build && npm run start -- --port 3000",
      url: FRONTEND_URL,
      env: { NEXT_PUBLIC_API_BASE_URL: REAL_API_URL, NEXT_DIST_DIR: ".next-real" },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
