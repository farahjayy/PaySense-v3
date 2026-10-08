"""The committed generated artefacts must match what the code and parameters produce today.

If one of these fails after a parameter or generator change, regenerate the artefact
(`python -m ml.datagen.personas`, `python -m ml.datagen.export`, `python -m ml.datagen.report`)
and commit it with the change; a stale artefact would otherwise pass as current.
"""

import json
from pathlib import Path

from ml.datagen.params import load_params
from ml.datagen.personas import PERSONA_SEEDS, build_persona_profile, render_csv
from ml.datagen.rng import profile_rng

ROOT = Path(__file__).resolve().parents[3]
PARAMS = load_params()


def test_the_committed_persona_csvs_match_a_fresh_generation():
    for persona in PERSONA_SEEDS:
        committed = (ROOT / "data" / "personas" / f"{persona}.csv").read_bytes()
        fresh = render_csv(build_persona_profile(PARAMS, persona)).encode("utf-8")
        assert committed == fresh, persona


def test_the_committed_manifest_and_report_were_made_with_todays_parameters():
    manifest = json.loads((ROOT / "data" / "synthetic" / "MANIFEST.json").read_text("utf-8"))
    readme = (ROOT / "reports" / "datagen" / "README.md").read_text("utf-8")

    assert manifest["params_hash"] == PARAMS.hash()
    assert PARAMS.hash() in readme


def test_the_random_streams_are_pinned_so_a_numpy_change_is_noticed():
    drawn = round(float(profile_rng(7, 3, "income").random()), 12)

    assert drawn == 0.649241702234
