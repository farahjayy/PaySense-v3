"""Generate THIRD_PARTY.md from the installed dependencies (WP10).

    cd backend && uv run python scripts/gen_third_party.py

Python licences come from `pip-licenses` (run through `uv run --with`, so it is not a project
dependency); frontend licences from the
installed production tree (`frontend_rows`).
Each Python package is marked runtime (the server needs it) or dev/ml (tests and offline
training only). The datasets section is fixed text: neither dataset is committed.
"""

# ruff: noqa: E501  (the datasets table is Markdown; its rows cannot wrap)
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATASETS = """## Datasets (not committed; fetched by scripts)

Both are real transaction data of other people, used **only as Engine 1 benchmarks** (D-25);
neither models the target population. Details and checksums: `data/external/README.md`.

| Dataset | Licence | Fetch |
|---|---|---|
| MoneyData (Firat et al., EuroVis 2023): one UK retail account | CC BY 4.0 | `data/external/moneydata/download.py` |
| Berka / PKDD'99: 4,500 anonymised Czech accounts | None stated by the CTU page; published for research use | `data/external/berka/download.py` |

No real personal financial data is in this repository; every persona and training profile is
synthetic (D-14)."""

NOTES = """## Notes on specific licences

- **`@img/sharp-libvips-*` (LGPL-3.0-or-later)** is a prebuilt native library that Next.js's
  optional image optimiser (`sharp`) loads dynamically. It is used unmodified and is not
  bundled into PaySense's own code; LGPL permits this. Its source is at
  https://github.com/lovell/sharp-libvips.
- **`caniuse-lite` (CC-BY-4.0)** is browser-support data used at build time by the CSS
  toolchain. Attribution: data from caniuse.com by Alexis Deveria.
- Python packages marked *dev/ml* are used only for tests and offline training; they are not
  part of the deployed server.
- **Fonts: Bricolage Grotesque and Figtree (SIL Open Font License 1.1)**, used on the login
  page through `next/font/google`, which downloads them at build time and serves them from the
  app's own domain. They are used unmodified. Licence: https://openfontlicense.org."""


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)  # noqa: S603
    if result.returncode != 0:
        sys.exit(f"{cmd[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def _runtime_names() -> set[str]:
    out = _run(
        ["uv", "export", "--format", "requirements-txt", "--no-hashes", "--no-emit-project",
         "--no-default-groups"],
        ROOT / "backend",
    )  # fmt: skip
    names = set()
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-")):
            names.add(line.split("==")[0].split("[")[0].split(" ")[0].lower().replace("_", "-"))
    return names


def python_rows() -> list[str]:
    runtime = _runtime_names()
    data = json.loads(
        _run(
            ["uv", "run", "--with", "pip-licenses", "pip-licenses", "--format=json", "--with-urls"],
            ROOT / "backend",
        )
    )
    tooling = {"pip-licenses", "prettytable", "wcwidth", "paysense-backend"}
    rows = []
    for item in sorted(data, key=lambda d: d["Name"].lower()):
        key = item["Name"].lower().replace("_", "-")
        if key in tooling:
            continue
        group = "runtime" if key in runtime else "dev/ml"
        rows.append(f"| {item['Name']} | {item['Version']} | {item['License']} | {group} |")
    return rows


def _resolve(name: str, start: Path) -> Path | None:
    """Node's lookup: the nearest `node_modules/<name>` from `start` upwards (follows pnpm links)."""
    for folder in (start, *start.parents):
        candidate = folder / "node_modules" / name
        if candidate.is_dir():
            return candidate.resolve()
    return None


def frontend_rows() -> list[str]:
    # Walked by hand: `pnpm licenses list --prod` drops transitive optional dependencies (sharp's
    # LGPL libvips binary, which Next loads at runtime). Follows dependencies, optional
    # dependencies installed on this platform, and required peers; never devDependencies.
    seen: dict[Path, dict] = {}
    queue = [(ROOT / "frontend").resolve()]
    while queue:
        folder = queue.pop()
        manifest = json.loads((folder / "package.json").read_text(encoding="utf-8"))
        optional_peers = {
            k for k, v in manifest.get("peerDependenciesMeta", {}).items() if v.get("optional")
        }
        wanted = {
            *manifest.get("dependencies", {}),
            *manifest.get("optionalDependencies", {}),
            *(set(manifest.get("peerDependencies", {})) - optional_peers),
        }
        for name in wanted:
            found = _resolve(name, folder)
            if found and found not in seen:
                seen[found] = json.loads((found / "package.json").read_text(encoding="utf-8"))
                queue.append(found)
    rows = set()
    for item in seen.values():
        licence = item.get("license", "UNKNOWN")
        if isinstance(licence, dict):
            licence = licence.get("type", "UNKNOWN")
        rows.add(f"| {item['name']} | {item['version']} | {licence} |")
    return sorted(rows, key=str.lower)


def main() -> int:
    py = python_rows()
    fe = frontend_rows()
    text = "\n".join(
        [
            "# Third-party software and data",
            "",
            "> Generated by `backend/scripts/gen_third_party.py`; do not edit by hand.",
            "> PaySense itself is licensed under Apache-2.0 (see `LICENSE` and `NOTICE`).",
            "",
            DATASETS,
            "",
            NOTES,
            "",
            f"## Python packages ({len(py)})",
            "",
            "| Package | Version | Licence | Used by |",
            "|---|---|---|---|",
            *py,
            "",
            f"## Frontend packages, production tree ({len(fe)})",
            "",
            "| Package | Version | Licence |",
            "|---|---|---|",
            *fe,
            "",
        ]
    )
    (ROOT / "THIRD_PARTY.md").write_text(text, encoding="utf-8")
    print(f"THIRD_PARTY.md: {len(py)} Python, {len(fe)} frontend packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
