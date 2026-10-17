# Execution — WP10 Repo, licence and docs

> Companion plan: `refdocs/plans/2026-10-18-wp10-repo-licence-docs.md`.

## Tasks
1. `backend/scripts/gen_third_party.py` → `THIRD_PARTY.md`. Verify: `cd backend && uv run python scripts/gen_third_party.py` (118 Python, 71 frontend packages; dataset text taken from `data/external/README.md`).
2. Torch-free run: in a separate environment `uv run --no-group ml pytest -q --ignore=tests/ml`. Fixes: `ml/uat/errors.py` (the persona shifter no longer imports scipy and yaml through `ml.uat.load`); `tests/engines/test_artefact.py` skips without `skl2onnx`.
3. `git ls-files` shows no `coverage/`, `*.tsbuildinfo`, `.next/` or `__pycache__`; `git log --all -- progress_material` is empty.
4. README, CREDITS.md, file-structure.md.

## Deviations
- `THIRD_PARTY.md` and its script were committed inside the WP16 merge commit (staged together by mistake); their changelog entry is this package's.
- The first draft of the datasets text in the generator described MoneyData as calibrating the synthetic population; checked against `data/external/README.md` and corrected (both datasets are Engine 1 benchmarks only, D-25) before the file was generated.

## Wrap-up
CHANGELOG, STATUS, questions (NOTICE name); commit and push.
