import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

// A machine whose Playwright browsers do not match this version (e.g. a pre-provisioned cloud
// container) points PW_CHROMIUM_PATH at its own Chromium instead of downloading one.
const launchOptions = process.env.PW_CHROMIUM_PATH
  ? { executablePath: process.env.PW_CHROMIUM_PATH }
  : {};

// Ports are fixed and unusual so a running dev server on 3000/8000 is never reused by mistake.
const FRONTEND_URL = "http://localhost:3100";
const API_URL = "http://localhost:8100";
const uvBin = path.join(os.homedir(), ".local", "bin");
const pathWithUv = `${uvBin}${path.delimiter}${process.env.PATH ?? ""}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // The dashboard forecast is CPU-bound in one stub-backend process; with every worker signing in
  // at once a slower machine (the author's Windows laptop) queues it past the 5 s default.
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: FRONTEND_URL, trace: "retain-on-failure", launchOptions },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      // Real FastAPI app on an in-memory database seeded with the "e2e" tester. E2E_FAKE_LLM runs
      // the assistant on a scripted model (never a real provider) for the assistant journey.
      command: "uv run uvicorn tests.e2e_server:app --port 8100",
      cwd: "../backend",
      url: `${API_URL}/api/health`,
      env: { PATH: pathWithUv, E2E_FAKE_LLM: "1" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // The production build, not `next dev`: the Content-Security-Policy (no eval, nonce-only
      // scripts) must be exercised exactly as it will be served.
      command: "pnpm build && pnpm start --port 3100",
      url: FRONTEND_URL,
      env: { NEXT_PUBLIC_API_BASE_URL: API_URL, NEXT_DIST_DIR: ".next-e2e" },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
