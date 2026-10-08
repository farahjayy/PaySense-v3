// Generate (or drift-check) lib/api/schema.d.ts from the backend's OpenAPI document (ADR D-18).
//
//   npm run gen:api     regenerate lib/api/schema.d.ts
//   npm run check:api   fail (exit 1) if the committed file differs from a fresh generation
//
// The spec comes from `uv run python -m app.export_openapi`, which needs no database,
// credentials or running server. Requires `uv` on PATH.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(frontendDir, "..", "backend");
const committed = join(frontendDir, "lib", "api", "schema.d.ts");
const check = process.argv.includes("--check");

const scratch = mkdtempSync(join(tmpdir(), "paysense-api-"));
const run = (command, args, cwd) =>
  execFileSync(command, args, { cwd, stdio: ["ignore", "inherit", "inherit"], shell: false });
const normalise = (text) => text.replace(/\r\n/g, "\n");

try {
  const spec = join(scratch, "openapi.json");
  const generated = join(scratch, "schema.d.ts");
  run("uv", ["run", "python", "-m", "app.export_openapi", spec], backendDir);
  const cli = join(frontendDir, "node_modules", "openapi-typescript", "bin", "cli.js");
  run(process.execPath, [cli, spec, "-o", generated], frontendDir);
  const fresh = normalise(readFileSync(generated, "utf8"));
  if (check) {
    let current = "";
    try {
      current = normalise(readFileSync(committed, "utf8"));
    } catch {
      /* missing file counts as drift */
    }
    if (current !== fresh) {
      console.error("lib/api/schema.d.ts is out of date with the backend. Run: npm run gen:api");
      process.exitCode = 1;
    } else {
      console.log("lib/api/schema.d.ts matches the backend OpenAPI document.");
    }
  } else {
    writeFileSync(committed, fresh, "utf8");
    console.log("Wrote lib/api/schema.d.ts");
  }
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
