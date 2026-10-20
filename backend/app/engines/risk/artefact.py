"""The served risk model: load it, check it matches the running code, predict and explain.

The artefact is a folder (`models/engine2/<version>/`) holding `model.onnx` (the trained
classifier, run with ONNX Runtime so no training library enters the API process, D-15) and
`metadata.json` (the calibrator as plain numbers, the reference student for explanations, and
everything the model was built against). No pickle anywhere.

The server must refuse a model that was built against different code (D-09, the v1 failure): the
feature schema hash, the feature order, the simulation constants that decided every label, and the
exact forecast network files must all equal what is running now. Any difference raises
`ArtefactError`, which stops the API from starting.
"""

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime

from app.engines.forecasting.bands import BAND_FILE, load_band_rule, text_digest
from app.engines.forecasting.onnx_model import MODEL_DIR as ENGINE1_DIR
from app.engines.forecasting.population import PopulationError, load_population
from app.engines.forecasting.service import DASHBOARD_MONTHS
from app.engines.forecasting.serving import ARTEFACT_VERSION as ENGINE1_VERSION
from app.engines.forecasting.serving import SERVED_MODEL
from app.engines.forecasting.simulate import BOOTSTRAP_BLOCK, RISK_CHECK_MAX_WEEKS
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH
from app.engines.risk.shapley import baseline_shapley

logger = logging.getLogger("paysense")

MODEL_ROOT = Path(__file__).resolve().parents[3] / "models" / "engine2"
MODEL_FILE = "model.onnx"
METADATA_FILE = "metadata.json"
# What the model's output is (engine v3, D-62): "p_with", the chance of running short with the
# purchase (v1, v2); or "two_part", q, the chance the purchase makes short a simulated future that
# was not short without it, which the check composes with the simulated chance without it.
TARGETS = ("p_with", "two_part")


def _population_sha256() -> str | None:
    if not BAND_FILE.exists():
        return None
    population = load_band_rule(BAND_FILE).population
    return population.sha256 if population is not None else None


def live_constants() -> dict[str, Any]:
    """What every label depended on besides the network files. The band table (WP16, C2) is
    recorded by its digest: a label made with other bands is a different label. The band rule
    also names its clip mode and its population error record (engine v3, D-60/D-61); the record's
    digest is recorded on its own as well, so a model made before it existed (which recorded
    nothing) still loads only while no record is in use."""
    return {
        "RISK_CHECK_MAX_WEEKS": RISK_CHECK_MAX_WEEKS,
        "DASHBOARD_MONTHS": DASHBOARD_MONTHS,
        "BAND_RULE_SHA256": text_digest(BAND_FILE) if BAND_FILE.exists() else None,
        "BOOTSTRAP_BLOCK": BOOTSTRAP_BLOCK,
        "POPULATION_RECORD_SHA256": _population_sha256(),
    }


def clamp_probability(value: float) -> float:
    """A probability must be in [0, 1]; float32 trees can land a hair outside."""
    return float(min(1.0, max(0.0, value)))


class ArtefactError(RuntimeError):
    """The risk model cannot be served; the message says why."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256s(path: Path) -> set[str]:
    """Digests of a text file as checked out with LF and with CRLF line endings.

    Git converts line endings on checkout, so a model trained on Windows records the CRLF digest
    and a Linux checkout (the Render build) holds the LF file. The settings are the same either way.
    """
    lf = path.read_bytes().replace(b"\r\n", b"\n")
    return {hashlib.sha256(lf).hexdigest(), hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()}


def _read_metadata(folder: Path) -> dict[str, Any]:
    path = folder / METADATA_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise ArtefactError(f"cannot read the model metadata at {path}: {err}") from err


def _check_population_record() -> None:
    """The band rule's population record must be readable and match its digest now, not on the
    first request from a student with under 26 weeks of history (ml-audit C9)."""
    if not BAND_FILE.exists():
        return
    rule = load_band_rule(BAND_FILE)
    if rule.population is None:
        return
    try:
        load_population(rule.population_path(), rule.population.sha256)
    except PopulationError as err:
        raise ArtefactError(f"the population record cannot be used: {err}") from err


def _check_matches_running_code(meta: Mapping[str, Any], folder: Path) -> None:
    if meta.get("feature_schema_hash") != FEATURE_SCHEMA_HASH:
        raise ArtefactError(
            f"the model was built for feature schema {meta.get('feature_schema_hash')!r} but this "
            f"code computes {FEATURE_SCHEMA_HASH!r}; retrain or redeploy matching code"
        )
    if list(meta.get("feature_names", [])) != list(FEATURE_NAMES):
        raise ArtefactError("the model's feature order differs from the code's feature order")
    recorded = meta.get("serving_constants", {})
    for name, live in live_constants().items():
        if recorded.get(name) != live:
            raise ArtefactError(
                f"{name} was {recorded.get(name)!r} when the model's labels were made but is "
                f"{live!r} now"
            )
    _check_population_record()
    label = meta.get("label", {})
    if label.get("horizon_max_weeks") != RISK_CHECK_MAX_WEEKS:
        raise ArtefactError(
            f"the labels were made with a {label.get('horizon_max_weeks')!r}-week horizon limit, "
            f"this code uses {RISK_CHECK_MAX_WEEKS}"
        )
    for filename, digest in (label.get("served_model_files") or {}).items():
        if Path(filename).name != filename or filename in {"", ".", ".."} or "\\" in filename:
            raise ArtefactError(f"the forecast file name {filename!r} is not a plain file name")
        live_path = ENGINE1_DIR / ENGINE1_VERSION / filename
        if not live_path.exists() or _sha256(live_path) != digest:
            raise ArtefactError(
                f"the labels were made with a different forecast model file ({filename}); "
                "the served forecast model has changed since"
            )
    if label.get("served_model") != SERVED_MODEL:
        raise ArtefactError(
            f"the labels were made with forecast model {label.get('served_model')!r}, "
            f"but {SERVED_MODEL!r} is serving now"
        )
    settings_path = ENGINE1_DIR / ENGINE1_VERSION / "metadata.json"
    if not settings_path.exists() or label.get("engine1_metadata_sha256") not in text_sha256s(
        settings_path
    ):
        raise ArtefactError(
            "the forecast settings (window, horizon, scaling) differ from those the labels "
            "were made with"
        )
    if not label.get("served_model_files"):
        raise ArtefactError("the artefact does not record which forecast model made its labels")
    model_path = folder / MODEL_FILE
    if not model_path.exists() or _sha256(model_path) != meta.get("onnx_sha256"):
        raise ArtefactError("the model file does not match the checksum recorded at export")


class OnnxPredictor:
    """Calibrated probability from the Engine 2 features, and which features pushed it up."""

    def __init__(self, folder: Path, meta: Mapping[str, Any]) -> None:
        self.version: str = str(meta["version"])
        self.feature_schema_hash: str = str(meta["feature_schema_hash"])
        self.family: str = str(meta.get("family", ""))
        self.target: str = str(meta.get("target", "p_with"))
        if self.target not in TARGETS:
            raise ArtefactError(f"unknown model target {self.target!r}; expected one of {TARGETS}")
        metrics = meta.get("metrics", {})
        self.summary: dict[str, Any] = {
            "family": self.family,
            "development_profiles": meta.get("training", {}).get("development_profiles"),
            "lockbox_brier": (metrics.get("lockbox_calibrated") or {}).get("brier"),
            "constant_brier": metrics.get("lockbox_constant_brier"),
        }
        self._calibrator: Mapping[str, Any] = meta["calibrator"]
        self._eps = float(meta.get("logit_eps", 1e-6))
        self._baseline = np.array([meta["baseline"][name] for name in FEATURE_NAMES], dtype=float)
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1  # one request at a time on a small host
        self._session = onnxruntime.InferenceSession(
            str(folder / MODEL_FILE), sess_options=options, providers=["CPUExecutionProvider"]
        )
        shape = self._session.get_inputs()[0].shape
        if shape[-1] != len(FEATURE_NAMES):
            raise ArtefactError(
                f"the model takes {shape[-1]} inputs, expected {len(FEATURE_NAMES)}"
            )
        self._input = self._session.get_inputs()[0].name
        names = [o.name for o in self._session.get_outputs()]
        self._output = "probabilities" if "probabilities" in names else names[-1]

    # ------------------------------------------------------------------ prediction
    def _raw(self, batch: np.ndarray) -> np.ndarray:
        out = self._session.run([self._output], {self._input: batch.astype(np.float32)})[0]
        return np.asarray(out, dtype=float)[:, 1]

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        kind = self._calibrator["kind"]
        if kind == "none":
            return raw
        if kind == "platt":
            clipped = np.clip(raw, self._eps, 1 - self._eps)
            logit = np.log(clipped / (1 - clipped))
            return 1 / (
                1 + np.exp(-(self._calibrator["coef"] * logit + self._calibrator["intercept"]))
            )
        if kind == "isotonic":
            return np.interp(raw, self._calibrator["x"], self._calibrator["y"])
        raise ArtefactError(f"unknown calibration {kind!r}")

    def predict_batch(self, batch: np.ndarray) -> np.ndarray:
        return self._calibrate(self._raw(np.asarray(batch, dtype=float)))

    def predict(self, vector: Sequence[float]) -> float:
        return clamp_probability(float(self.predict_batch(np.asarray([vector], dtype=float))[0]))

    # ------------------------------------------------------------------ explanation
    def contributions(self, vector: Sequence[float]) -> list[float]:
        """Exact Shapley values against the reference student, on the scale of `predict` (D-40)."""
        values = baseline_shapley(
            self.predict_batch, np.asarray(vector, dtype=float), self._baseline
        )
        return [float(v) for v in values]


def load_engine2(folder: Path) -> OnnxPredictor:
    """Load one version folder, or raise `ArtefactError` saying what is wrong."""
    meta = _read_metadata(folder)
    _check_matches_running_code(meta, folder)
    try:
        return OnnxPredictor(folder, meta)
    except ArtefactError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as err:
        raise ArtefactError(f"the model at {folder} could not be loaded: {err!r}") from err


def load_if_present(root: Path = MODEL_ROOT) -> OnnxPredictor | None:
    """The newest version under `root`; None when nothing is deployed there (the risk check then
    says it is unavailable). A version that is there but wrong stops start-up."""
    folders = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    unfinished = [p.name for p in folders if not (p / METADATA_FILE).exists()]
    if unfinished:
        raise ArtefactError(
            f"model folder(s) {unfinished} have no {METADATA_FILE}: finish or remove them, "
            "rather than quietly serving an older version"
        )
    versions = folders
    if not versions:
        logger.warning("no risk model found under %s: the risk check will answer 503", root)
        return None
    return load_engine2(max(versions, key=_version_key))


def _version_key(folder: Path) -> tuple[tuple[int, ...], str]:
    """v2 beats v1 and v10 beats v9; v1.1 is between v1 and v2."""
    numbers = tuple(int(n) for n in re.findall(r"\d+", folder.name))
    return (numbers or (-1,), folder.name)
