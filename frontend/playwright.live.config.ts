import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * The assistant with the LIVE model (opt-in; CI never runs this). The backend is the in-memory
 * test app with the real served risk model and the provider configured in the environment
 * (`backend/tests/live_server.py`); screenshots and the replies go to `evidence/live-browser/`.
 *
 *   cd frontend && pnpm exec playwright test -c playwright.live.config.ts
 */
const launchOptions = process.env.PW_CHROMIUM_PATH
  ? { executablePath: process.env.PW_CHROMIUM_PATH }
  : {};
const FRONTEND_URL = "http://localhost:3100"; // the test app's CORS origin
const API_URL = "http://localhost:8100";
const uvBin = path.join(os.homedir(), ".local", "bin");
const pathWithUv = `${uvBin}${path.delimiter}${process.env.PATH ?? ""}`;

export default defineConfig({
  testDir: "./tests/e2e-live",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: FRONTEND_URL, trace: "retain-on-failure", launchOptions },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run uvicorn tests.live_server:app --port 8100",
      cwd: "../backend",
      url: `${API_URL}/api/health`,
      env: { PATH: pathWithUv },
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: "pnpm build && pnpm start --port 3100",
      url: FRONTEND_URL,
      env: { NEXT_PUBLIC_API_BASE_URL: API_URL, NEXT_DIST_DIR: ".next-live" },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
