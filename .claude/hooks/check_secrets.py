#!/usr/bin/env python3
"""
Secret-literal guard — PreToolUse hook on Write/Edit/MultiEdit.

Reads Claude Code's hook JSON on stdin. For file-write tools, scans the content
being written for key-shaped literals. On a match, exits 2 with a message naming
the file, the line, and the fix — so the model self-corrects without the user
having to intervene.

Scaffolded by /newproject. TUNE THIS FILE:
  - Delete PATTERNS for providers this project does not use. An AWS regex in a
    project with no AWS is pure false-positive surface.
  - Add this project's own vendor key formats.
  - Point FIX_LINES at where secrets actually belong here.

Standard library only, by design — a hook that needs `pip install` breaks on a
fresh clone.
"""

from __future__ import annotations

import json
import os
import re
import sys

# (label, regex) — order matters only for message readability.
# Trimmed for PaySense v3 (2026-10-08): Supabase keys (legacy JWT service_role and
# new sb_secret_ format), the session-signing secret, the optional Anthropic key,
# GitHub tokens (the author pushes to GitHub), private keys. Dropped: AWS, OpenAI,
# Slack, Google, Stripe (unused), and the 32-char hex pattern (model metadata
# stores feature-schema hashes that would trip it).
PATTERNS: list[tuple[str, str]] = [
    ("JWT token (eyJ…) — e.g. a Supabase service_role key or a session token",
     r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),
    ("Supabase secret key",
     r"sb_secret_[A-Za-z0-9_\-]{20,}"),
    ("High-entropy literal near key/secret/token/password",
     r"(?:api[_-]?key|secret|token|password)[^A-Za-z0-9\n]{1,8}[A-Za-z0-9+/=_\-]{32,}"),
    ("GitHub PAT",         r"gh[pousr]_[A-Za-z0-9]{30,}"),
    ("Anthropic API key",  r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    ("Private key block",  r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
]

# Where secrets are supposed to live in THIS project.
FIX_LINES = [
    "  - Local dev  -> put the value in the repo-root .env (gitignored) and read it via backend/app/core/settings.py.",
    "  - Deployed   -> set it in the Render (backend) or Vercel (frontend) environment-variable settings.",
    "  - Document the variable NAME in the root .env.example, the app's own .env.example and docs/env_setup.md. This repo is PUBLIC.",
]

ALLOW_MARK = "pragma: allowlist secret"

# Files that are allowed to contain secret-shaped strings.
ALLOWED_BASENAMES = {"check_secrets.py"}
ALLOWED_PREFIXES = (".env",)
# Lockfiles and vendored code produce endless false positives.
SKIP_SUBSTRINGS = ("node_modules/", "/vendor/", ".lock", "-lock.json")


def extract(data: dict) -> tuple[str, str] | None:
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    if tool == "Write":
        return ti.get("file_path", "?"), ti.get("content", "") or ""
    if tool == "Edit":
        return ti.get("file_path", "?"), ti.get("new_string", "") or ""
    if tool == "MultiEdit":
        edits = ti.get("edits", []) or []
        return ti.get("file_path", "?"), "\n".join((e.get("new_string", "") or "") for e in edits)
    return None


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        # Fail open: never block work because the hook could not parse its input.
        print(f"[check_secrets] warning: malformed hook JSON ({e}); pass-through.", file=sys.stderr)
        return 0

    pair = extract(data)
    if pair is None:
        return 0
    path, content = pair

    norm = path.replace("\\", "/")
    base = os.path.basename(norm)
    # .env.example is committed to a public repo, so it is scanned like source.
    if base in ALLOWED_BASENAMES or (base.startswith(ALLOWED_PREFIXES) and base != ".env.example"):
        return 0
    if any(frag in norm for frag in SKIP_SUBSTRINGS):
        return 0

    lines = [ln for ln in content.splitlines() if ALLOW_MARK not in ln]

    findings: list[tuple[str, list[tuple[int, str]]]] = []
    for label, pattern in PATTERNS:
        hits: list[tuple[int, str]] = []
        for i, line in enumerate(lines, start=1):
            if re.search(pattern, line):
                hits.append((i, line.strip()[:160]))
                if len(hits) >= 3:
                    break
        if hits:
            findings.append((label, hits))

    if not findings:
        return 0

    msg = [f"BLOCKED: secret literal detected in {path}", ""]
    for label, hits in findings:
        msg.append(f"  {label}:")
        msg.extend(f"    line {i}: {snippet}" for i, snippet in hits)
        msg.append("")
    msg.append("Fix:")
    msg.extend(FIX_LINES)
    msg += ["", f"False positive? Append '# {ALLOW_MARK}' to that line. Use sparingly."]
    print("\n".join(msg), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
