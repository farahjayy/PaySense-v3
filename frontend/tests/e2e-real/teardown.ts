import { execFileSync } from "node:child_process";
import path from "node:path";

import { ACCOUNT_FILE } from "../../playwright.real.config";

/** Delete the throwaway account; every row it wrote goes with it (on delete cascade). */
export default function globalTeardown() {
  execFileSync("uv", ["run", "python", "scripts/e2e_real_account.py", "delete", "--file", ACCOUNT_FILE], {
    cwd: path.resolve(__dirname, "../../../backend"),
    stdio: "inherit",
  });
}
