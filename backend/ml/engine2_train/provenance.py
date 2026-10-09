"""What a result was made with: library versions, the git commit, a file hash (audit L3)."""

import hashlib
import platform
import shutil
import subprocess
from importlib import metadata
from pathlib import Path

PACKAGES = (
    "numpy",
    "scipy",
    "scikit-learn",
    "xgboost",
    "lightgbm",
    "optuna",
    "onnxruntime",
    "torch",
)
NOT_INSTALLED = "not installed"
GIT_TIMEOUT_SECONDS = 10


def library_versions() -> dict[str, str]:
    found = {"python": platform.python_version()}
    for name in PACKAGES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = NOT_INSTALLED
    return found


def git_commit(repo: Path | None = None) -> str | None:
    """The HEAD commit, with `+dirty` when tracked files under `backend/` have uncommitted
    changes (the frontend is another tree and does not affect a result)."""
    git = shutil.which("git")
    if git is None:
        return None
    where = str(repo or Path(__file__).resolve().parent)

    def ask(*args: str) -> str:
        return subprocess.run(  # noqa: S603 - a fixed git command, no user input
            [git, *args], cwd=where, capture_output=True, text=True,
            timeout=GIT_TIMEOUT_SECONDS, check=True,
        ).stdout.strip()  # fmt: skip

    try:
        head = ask("rev-parse", "HEAD")
        changed = ask("status", "--porcelain", "--untracked-files=no", "--", ":/backend")
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{head}+dirty" if changed else head


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()
