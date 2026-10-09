import os from "node:os";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

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
  reporter: [["list"]],
  use: { baseURL: FRONTEND_URL, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      // Real FastAPI app on an in-memory database seeded with the "e2e" tester.
      command: "uv run uvicorn tests.e2e_server:app --port 8100",
      cwd: "../backend",
      url: `${API_URL}/api/health`,
      env: { PATH: pathWithUv },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // The production build, not `next dev`: the Content-Security-Policy (no eval, nonce-only
      // scripts) must be exercised exactly as it will be served.
      command: "npm run build && npm run start -- --port 3100",
      url: FRONTEND_URL,
      env: { NEXT_PUBLIC_API_BASE_URL: API_URL, NEXT_DIST_DIR: ".next-e2e" },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
