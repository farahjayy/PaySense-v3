import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GIT = shutil.which("git") or "git"


def ignored(path: str) -> bool:
    result = subprocess.run(  # noqa: S603 - a fixed git command on repository paths
        [GIT, "check-ignore", "-q", path], cwd=ROOT, check=False
    )
    return result.returncode == 0


def test_the_label_file_and_the_run_outputs_are_never_committed():
    assert ignored("data/engine2/labels.jsonl")
    assert ignored("data/engine2/labels.run.json")
    assert ignored("data/engine2/runs/full/results.json")
    assert ignored("data/engine2/runs/full/final_model.joblib")


def test_only_the_small_label_manifest_is_committed():
    assert not ignored("data/engine2/MANIFEST.json")
