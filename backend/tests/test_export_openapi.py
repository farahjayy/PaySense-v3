import json
import subprocess
import sys
from pathlib import Path

from app.export_openapi import build_openapi, write_openapi

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_spec_is_built_without_any_environment_variables():
    spec = build_openapi()

    assert spec["info"]["title"] == "PaySense API"
    assert "/api/auth/login" in spec["paths"]


def test_spec_is_deterministic():
    assert json.dumps(build_openapi(), sort_keys=True) == json.dumps(
        build_openapi(), sort_keys=True
    )


def test_write_openapi_creates_parent_dirs_and_a_trailing_newline(tmp_path):
    target = tmp_path / "nested" / "openapi.json"

    write_openapi(target)

    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["paths"]


def test_module_runs_as_a_script_from_an_empty_environment(tmp_path):
    target = tmp_path / "out.json"

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.export_openapi", str(target)],
        cwd=BACKEND_DIR,
        env={"PATH": "", "SYSTEMROOT": "C:\\Windows"},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(target.read_text(encoding="utf-8"))["paths"]
