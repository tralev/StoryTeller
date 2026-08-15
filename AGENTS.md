# Repository Guidelines

## Project Structure & Module Organization

Core Python code lives in `src/`. Important areas include `src/worldgen/` for
deterministic procedural generation, `src/narrative/` for story construction,
`src/storage/` for package persistence, and `src/application/` for production
workflows. Tests mirror these domains under `tests/`; shared fixtures belong in
`tests/fixtures/`. Specifications and the active implementation roadmap are in
`docs/`. Platform clients and packaging live in `ios/`, `droid/`, `mac/`, `lin/`,
and `win/`. Keep generated outputs, caches, and local runs in `tmp/`.

## Build, Test, and Development Commands

- `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` installs the
  project and development tools.
- `.venv/bin/python -m src.cli --help` runs the Forge CLI from the checkout.
- `.venv/bin/pytest -q -m "not integration"` runs the normal test suite.
- `.venv/bin/pytest -q -m determinism` runs reproducibility checks.
- `.venv/bin/mypy src scripts tests` performs strict type checking.
- `.venv/bin/ruff check src tests scripts` checks formatting-related lint rules.
- `.venv/bin/python -m src.cli worldgen conformance check` validates worldgen
  contracts and generated coverage evidence.
- `.venv/bin/python scripts/audit_v2_schema_depth.py` is the P8.C1 closure gate;
  it intentionally fails while any v2 schema remains shallow or open-ended.

Prefer focused tests while iterating; run broader conformance and determinism
checks before handing off risky worldgen, storage, or schema changes.

## Coding Style & Naming Conventions

Use four-space indentation, type annotations, and a 100-character line limit.
Follow Python conventions: `snake_case` functions/modules, `PascalCase` classes,
and uppercase constants. Keep persisted records typed, immutable where practical,
and canonically ordered. World generation must use stable IDs, explicit fixed-point
math helpers, and seeded deterministic choices; avoid raw floating-point or
unordered iteration in authoritative output.

## Testing Guidelines

Pytest discovers `test_*.py` under `tests/`. Name tests after observable behavior,
for example `test_exploration_projector_rejects_teleportation`. Add focused unit
tests plus replay, conservation, corruption, or deterministic vectors when a
change affects persisted state. Mark expensive cases with `slow` or `integration`;
use `worldgen_property`, `history_property`, and `determinism` where applicable.

## Commit & Pull Request Guidelines

Recent commits use concise imperative or phase-prefixed subjects, such as
`Phase 5.6X: Artifact Provenance` or `Docs: track hardening recommendations`.
Keep commits scoped to one coherent change. Pull requests should explain intent,
list affected roadmap/contracts, report exact validation commands, and call out
schema or golden-vector changes. Include screenshots for UI changes and never
commit secrets, model weights, generated builds, or save files.
