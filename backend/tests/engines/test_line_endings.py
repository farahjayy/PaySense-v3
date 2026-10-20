"""D-52: text artefacts that are digested must be checked out with LF on every platform.

The loaders tolerate CRLF for the files they hash as text, but the pre-registered reports and the
Render build are made from LF. Pinning the end-of-line in `.gitattributes` removes the platform
difference instead of relying on each loader to forgive it.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend" / "models"
GIT = shutil.which("git") or "git"

TEXT_ARTEFACTS = sorted(
    p.relative_to(REPO).as_posix() for p in MODELS.rglob("*") if p.suffix in {".json", ".yaml"}
)


def _eol_attribute(path: str) -> str:
    out = subprocess.run(  # noqa: S603 - a fixed git command on repository paths
        [GIT, "check-attr", "eol", "--", path],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return out.strip().rsplit(": ", 1)[-1]


def test_there_are_text_artefacts_to_pin() -> None:
    assert any("rules/v3/population_errors.json" in p for p in TEXT_ARTEFACTS)
    assert any(p.endswith("engine1/band_inflation.json") for p in TEXT_ARTEFACTS)


@pytest.mark.parametrize("path", TEXT_ARTEFACTS)
def test_text_artefact_is_pinned_to_lf(path: str) -> None:
    assert _eol_attribute(path) == "lf"
