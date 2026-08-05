# Rewrite Phase 6: Persistence, Provenance, Resume, and `.story` v2 Freeze

## Mission

Freeze the sole supported `.story` v2 contract after Phases 2-5 stabilize.
Replace v1 persistence, schemas, fixtures, package layout, acceptance, and resume
logic. Delete v1 only after v2 acceptance fixtures pass.

## Entry state audit

| Current area | Disposition | Gap |
|---|---|---|
| `artifact_store.py` | Replace with typed repository | JSON-only write-through is not sufficient for domain/media provenance |
| `storage/checkpoint.py` | Rewrite schema/reconciliation | Node records lack full file/dependency fingerprints |
| `content_hash.py` | Retain canonical principle, rewrite inventory | v2 has explicit per-artifact provenance |
| `manifest_builder.py`, `packager.py` | Replace | v1 content/save layout and fields are obsolete |
| `package_acceptance.py` | Replace | Must validate all v2 domains, provenance, maps, and binary media |
| `schemas/*.json` | Replace with v2 set | Current schemas are narrative-first v1 |
| v1 fixtures/mobile copies | Delete after v2 corpus passes | Target supports v2 only |

## Frozen v2 layout

The phase must freeze the layout from `arch.md`: root manifest; separate
`world/` domain files; `narrative/` files; `assets/maps`, images, thumbnails, and
MIDI; no `save/`.

## Action plan

- [ ] **P6.1 (L, depends Phase 5):** Review representative worlds, confirm domain
  boundaries, enforce canonical JSON plus fixed 256x256 surface chunks,
  32x32x16 sparse local chunks, and year-0/ten-year/final snapshots, then freeze
  the frozen 128-bit type-prefixed ID grammar, RFC 8785 JCS, JSON Schema Draft
  2020-12, required/optional feature negotiation, and numeric security limits.
- [ ] **P6.2 (XL, depends P6.1):** Write v2 schemas for manifest, world index,
  terrain, hydrology, climate, biomes, resources, regions, routes, sites,
  civilizations, history, snapshots, local maps, Bible, reconciliation, style,
  story, graph, structured score,
  GM index, and artifact provenance.
- [ ] **P6.3 (L, depends P6.1):** Implement `ArtifactRepository` for atomic JSON
  and bytes with fsync, canonical paths, SHA-256, artifact IDs, dependency IDs,
  and producer fingerprints.
- [ ] **P6.4 (XL, depends P6.3):** Rewrite checkpoint DB with versioned migrations
  for run, phase, sub-step, and node records; store artifact references and
  structured failure/attempt history.
- [ ] **P6.5 (L, depends P6.4):** Implement dependency-aware resume
  reconciliation and downstream invalidation based on actual disk hashes.
- [ ] **P6.6 (L, depends P6.2,P6.3):** Replace manifest builder with a canonical
  complete inventory and provenance DAG; keep operational logs outside package.
- [ ] **P6.7 (L, depends P6.6):** Replace packager with deterministic staged ZIP
  creation and normalized paths, entries, timestamps, permissions, and encoding.
- [ ] **P6.8 (XL, depends P6.2,P6.7):** Replace acceptance to check ZIP safety and
  limits, v2-only version, every schema, inventory/hash/provenance, world
  invariants, graph references, maps, exact media coverage, PNGs, and MIDI.
- [ ] **P6.9 (M, depends P6.8):** Publish only by atomic rename after acceptance;
  return stable issue codes through application and CLI.
- [ ] **P6.10 (L, depends P6.2,P6.8):** Generate a shared v2 fixture corpus and
  machine-readable scenario catalog for Python/Android/iOS.
- [ ] **P6.11 (M, depends P6.10):** Add archive determinism, different-directory,
  worker-count, crash-window, and resume-equivalence gates.
- [ ] **P6.12 (M, depends P6.10):** Delete v1 schemas, fixtures, fixture copies,
  package generation/import paths, `save/` package logic, migration concepts,
  and narrative/procedural modes.
- [ ] **P6.13 (S, depends P6.12):** Make Forge reject v1 with
  `PACKAGE_UNSUPPORTED_VERSION` and regenerate-v2 guidance; provide no converter.

## Integrated `src/worldgen` rewrite work

Phase 6 freezes and packages the complete output of worldgen rewrite WP8.

- [ ] **P6.WG1 (L, depends Phase 5):** Freeze schemas for every required worldgen
  artifact kind, including chunks, registries, events, snapshots, local maps,
  opportunities, map layers, indexes, validation reports, and envelopes.
- [ ] **P6.WG2 (M, depends P6.WG1):** Freeze canonical integer-grid chunk layout,
  JSON encoding, ordering, identifiers, hashes, units, and artifact paths.
- [ ] **P6.WG3 (L, depends P6.WG1,P6.WG2):** Make package acceptance require the
  exact complete procedural inventory; unused cells, events, entities, and local
  maps cannot be pruned because narrative did not reference them.
- [ ] **P6.WG4 (L, depends P6.WG3):** Recompute domain/chunk hashes, validate the
  dependency DAG, replay history, rebuild indexes, and rerun macro/local
  reconciliation during acceptance.
- [ ] **P6.WG5 (M, depends P6.WG1-P6.WG4):** Add small, representative, large,
  corrupt, dependency-broken, replay-broken, index-broken, and incomplete-world
  packages to the shared corpus.
- [ ] **P6.WG6 (S, depends P6.WG5):** Delete `world_snapshot.schema.json` and the
  legacy snapshot adapter after all consumers use frozen v2 world artifacts.

The Phase 6 freeze includes the worldgen algorithm/content-registry versions and
golden vectors. Later algorithm evolution creates a new profile without changing
the meaning of existing package facts.

## Target provenance example

```json
{
  "artifact_id": "history_8ce91f0473d5a21bc7409e689c2f013a",
  "kind": "history",
  "path": "world/history/index.json",
  "sha256": "<64 hex>",
  "depends_on": [
    "civilizations_125fcad807a12b9e43db65c4a72e1180",
    "routes_5ec019da40678fb3127a9e8c42d1ab63"
  ],
  "producer": {
    "component": "history_simulator",
    "algorithm_version": 2,
    "fingerprint": "<sha256>"
  }
}
```

Resume decision:

```python
def reusable(ref: ArtifactRef, repo: ArtifactRepository, deps: set[str]) -> bool:
    return (
        set(ref.depends_on) == deps
        and repo.path_is_confined(ref.canonical_path)
        and repo.hash_matches(ref)
        and repo.validate(ref).is_valid
    )
```

## File operations

Replace all schemas and storage/packaging modules. Add v2 schema/domain modules,
fixture generator, scenario catalog, migrations only for internal checkpoint DB,
and acceptance security tests. Delete every v1 schema/fixture/import path only
after P6.10 passes.

## Focused tests

- Every schema valid/invalid fixture
- Provenance DAG completeness/cycles/broken IDs
- Atomic JSON/media/package crash windows
- Resume file/dependency/fingerprint mismatch
- Path traversal, symlink, duplicate path, bomb/limit cases
- RFC 8785 canonicalization vectors and Draft 2020-12 schema behavior
- ID length/alphabet/type-prefix and full SHA-256 rejection cases
- Sorted/unique feature arrays; unknown-required rejection and unknown-optional tolerance
- No arbitrary package-size ceiling; declared-size, free-space, nesting, parser,
  entry-count, and compression-amplification enforcement
- Complete domain/reference/world invariants
- Exact map/node media inventory and binary validation
- v1 rejection and absence of migration
- Archive canonical equivalence and informative first diff

## Required commands at phase exit

```bash
.venv/bin/python scripts/generate_v2_fixtures.py
.venv/bin/pytest -q tests/v2/test_schemas.py tests/v2/test_provenance.py
.venv/bin/pytest -q tests/v2/test_checkpoint_resume.py tests/v2/test_atomicity.py
.venv/bin/pytest -q tests/v2/test_package_acceptance.py tests/v2/test_security.py
.venv/bin/pytest -q tests/v2/test_determinism.py
.venv/bin/python -m src.cli validate-package tests/fixtures/v2/complete.story
.venv/bin/python -m src.cli inspect-package tests/fixtures/v2/complete.story --json
```

## Exit checklist

- [ ] v2 schemas and package layout are frozen and documented.
- [ ] Forge emits and accepts v2 only.
- [ ] Every artifact has hash, ID, dependencies, and producer fingerprint.
- [ ] Resume verifies actual bytes and invalidates downstream precisely.
- [ ] Package acceptance is consumer-equivalent and binary-aware.
- [ ] Shared v2 fixture/scenario corpus passes.
- [ ] v1 schemas, fixtures, package paths, and package migration concepts are
  deleted; only internal checkpoint-database schema upgrades remain.

## Phase 7 handoff

Phase 7 receives a frozen v2 schema bundle, reference validator, fixture corpus,
scenario catalog, stable errors, and no legacy compatibility requirement.
