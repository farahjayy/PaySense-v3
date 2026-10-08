"""The API must never depend on offline ML code (CLAUDE.md "Surfaces"): `ml/` imports `app/`,
never the reverse."""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
IMPORTS_ML = re.compile(r"^\s*(?:from|import)\s+ml(?:\.|\s|$)", re.MULTILINE)


def test_no_module_under_app_imports_ml():
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if IMPORTS_ML.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_the_ml_package_can_use_the_apps_domain_code():
    from app.domain import schedule  # noqa: F401
    from ml import datagen  # noqa: F401


OFFLINE_ONLY = re.compile(
    r"^\s*(?:from|import)\s+(?:torch|prophet|statsforecast)(?:\.|\s|$)", re.MULTILINE
)


def test_the_served_application_never_imports_the_offline_forecasting_stack():
    """torch alone pushes a process past Render's memory (D-15); the LSTM is served via ONNX."""
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if OFFLINE_ONLY.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
