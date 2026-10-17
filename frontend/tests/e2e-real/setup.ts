import { execFileSync } from "node:child_process";
import path from "node:path";

import { ACCOUNT_FILE } from "../../playwright.real.config";

/** Seed a throwaway account on the real database and shift a persona statement to today. */
export default function globalSetup() {
  execFileSync("uv", ["run", "python", "scripts/e2e_real_account.py", "create", "--out", ACCOUNT_FILE], {
    cwd: path.resolve(__dirname, "../../../backend"),
    stdio: "inherit",
  });
}
