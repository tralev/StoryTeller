# Rewrite Phase 9: Cross-Platform Hardening, Compliance, and Release

## Mission

Turn the rewritten system into a releasable free offline product. Close
determinism, security, resource, quality, documentation, licensing, store, and
physical-device evidence. No feature is “done” based only on mocks or source
scaffolding.

## Entry state audit

| Current area | Disposition | Gap addressed here |
|---|---|---|
| Unit/integration suite | Retain and reorganize | Need explicit default/provisioned/release gates |
| Docker and packaging scripts | Rewrite/revalidate | Need reproducible release evidence and Wine/native matrix |
| Competing documentation | Remove or replace with pointers to this authoritative set | Multiple truth sources are prohibited |
| Model download scripts | Consolidate | Need pinned registry, licenses, checksums, resume, and UI parity |
| Mobile source builds | Release harden | Need physical devices, offline/privacy/store evidence |
| Pre-rewrite audit gaps | Absorbed | All remaining tasks must close here or earlier |

## Action plan

- [ ] **P9.1 (M, depends Phases 1-8):** Define CI gates: static/unit, fake-backed
  contract, v2 cross-platform, provisioned real-model, packaging, security, and
  release-candidate physical/manual.
- [ ] **P9.2 (L, depends P9.1):** Make default non-model suite fully green and
  deterministic; isolate provisioned tests without hiding missing release assets.
- [ ] **P9.3 (XL, depends P9.1):** Run one complete real-model v2 generation;
  record git/config/prompt/schema/model hashes, load order, duration, peak RAM,
  package/content hashes, and logs.
- [ ] **P9.4 (L, depends P9.3):** Interrupt/resume the real run and compare
  canonical artifacts to an uninterrupted run.
- [ ] **P9.5 (L, depends P9.2):** Prove pure procedural cross-platform identity,
  fake archive identity, same-machine real-model identity, worker independence,
  and informative first-difference reports.
- [ ] **P9.6 (XL, depends Phase 6,7):** Complete package/import fuzzing and
  security corpus: paths, duplicate entries, links, bombs, JSON limits, hashes,
  provenance, coordinates, events, media, and executable-content rejection.
- [ ] **P9.7 (L, depends Phase 8):** Measure physical Android/iOS model download,
  first chunk, throughput, RAM, storage, battery, thermal behavior, cancellation,
  and offline restart on the supported matrix.
- [ ] **P9.8 (M, depends P9.7):** Establish versioned performance baselines and
  regression budgets by hardware profile; do not impose a `.story` size cap.
- [ ] **P9.9 (L, depends Phase 8):** Prove no telemetry/cloud/background network
  traffic after model download; audit dependencies and platform permissions.
- [ ] **P9.10 (L, depends P9.6,P9.9):** Complete dated compliance record:
  privacy/support pages, mature/AI disclosures, store questionnaires, local
  flag/export behavior, data deletion, and policy review.
- [ ] **P9.11 (L, depends P9.10):** Freeze model allowlist with revision,
  checksum, source, license, notice, intended role, and release approval. Bundle
  all required third-party notices.
- [ ] **P9.12 (L, depends Phase 8):** Build signed/notarized or store-ready
  platform artifacts, validate Windows native/Wine, Linux, macOS, Android, iOS,
  and test clean installs/upgrades where platform rules require.
- [ ] **P9.13 (M, depends P9.3,P9.7):** Conduct human review of world plausibility,
  historical causality, Bible reconciliation, narrative branches, images, music,
  GM accuracy/character, spoilers, and prohibited content.
- [ ] **P9.14 (M, depends P9.1-P9.13):** Audit this authoritative documentation
  set against retained evidence; remove competing specifications elsewhereor replace them with a pointer to `docs/index.md`.
- [ ] **P9.15 (M, depends P9.14):** Generate contract-derived pipeline/CLI/archive
  documentation and fail CI on drift. Remove volatile test counts or generate them.
- [ ] **P9.16 (S, depends all):** Remove temporary adapters, dead v1 references,
  obsolete scripts, stale docs, copied fixtures, and ignored rewrite artifacts.

## Integrated `src/worldgen` rewrite work

Phase 9 absorbs worldgen rewrite WP9.

- [ ] **P9.WG1 (M, depends Phases 1-8):** Remove legacy `GridCell`,
  `WorldSnapshot`, LCG, compact generator modules, direct prompt adapter,
  narrative/procedural/hybrid modes, prototype schema, and compatibility tests.
- [ ] **P9.WG2 (L, depends P9.WG1):** Add worldgen property, mutation, fuzz,
  crash, resume, security, performance, and memory suites across small/default/
  large named profiles.
- [ ] **P9.WG3 (L, depends P9.WG2):** Prove fixed-point domain bytes match across
  supported Python/desktop platforms, worker counts, output paths, iteration-order
  perturbations, and resume; store first-difference evidence on failure.
- [ ] **P9.WG4 (L, depends P9.WG2):** Run a complete default 500-year world and
  record stage durations, peak memory, chunk/package sizes, invariant counts,
  ledger/snapshot replay, and artifact/profile/registry hashes.
- [ ] **P9.WG5 (L, depends P9.WG3,P9.WG4):** Carry that world through Bible,
  reconciliation, narrative, required local maps/media, packaging, and physical
  Android/iOS import and GM retrieval.
- [ ] **P9.WG6 (M, depends P9.WG1-P9.WG5):** Audit full-data retention and prove
  no procedural record was pruned merely because the story did not reference it.

Release is blocked by any remaining legacy import, float-valued canonical world
fact, replay mismatch, incomplete procedural inventory, or undocumented fallback.

## Release evidence record

```yaml
release: "2.0.0-rc1"
git_commit: "<sha>"
package_version: 2
models:
  text: {revision: "<rev>", sha256: "<sha>", license_revision: "<rev>"}
generation:
  run_spec_sha256: "<sha>"
  content_hash: "<sha>"
  package_sha256: "<sha>"
  duration_seconds: 0
  peak_ram_mb: 0
resume_equivalent: true
android: {imported: true, offline_gm: true, scenario_catalog: "pass"}
ios: {imported: true, offline_gm: true, scenario_catalog: "pass"}
compliance_reviewed_at: "YYYY-MM-DD"
```

## File operations

Add CI workflows, release evidence templates/records, security fuzz tests,
performance harnesses, privacy/support/license assets, store configuration, and
generated-doc checks. Replace old docs with reviewed target docs only at P9.14.
Remove all temporary adapters and stale v1/current-future mixed documentation.

## Required test matrix

- Python supported versions and desktop OS profiles
- Windows native and Wine
- Linux and macOS packaged Forge/launcher
- Android minimum and representative modern physical devices
- iOS minimum and representative modern physical devices
- Network-blocked post-download operation
- Low-space, cancellation, restart, and corrupted-input cases
- Real-model complete package imported on both Players

## Required commands at phase exit

```bash
./scripts/verify_release.sh --release-candidate
.venv/bin/mypy src scripts tests
.venv/bin/pytest -q -m "not integration"
.venv/bin/pytest -q -m integration --run-models
.venv/bin/pytest -q -m determinism
.venv/bin/pytest -q -m security
./scripts/build_all_desktop.sh
./scripts/test_wine.sh tmp/packages/storyteller-launcher.exe
./droid/gradlew -p droid testDebugUnitTest connectedDebugAndroidTest bundleRelease
xcodebuild -scheme StoryTeller -project ios/StoryTeller.xcodeproj test archive
.venv/bin/python scripts/verify_cross_platform_scenarios.py --release
.venv/bin/python scripts/check_docs_drift.py
```

Every wrapper command named here is implemented, documented, non-interactive in
CI, and returns nonzero on a failed sub-gate.

## Final completion checklist

- [ ] Default, provisioned, security, determinism, and platform gates pass.
- [ ] Real-model generation and resume equivalence are recorded.
- [ ] One accepted production v2 package imports on physical Android and iOS.
- [ ] Every node has a valid image, thumbnail, authoritative score, and derived MIDI.
- [ ] Strict spoiler sentinel tests pass at retrieval and prompt boundaries.
- [ ] GM download, chunks, persistence, RAM, thermal, and offline behavior pass.
- [ ] No telemetry, cloud save, remote inference, account, ad, or hidden network path exists.
- [ ] Model licenses/notices/checksums and store compliance are reverified.
- [ ] Windows/Wine/Linux/macOS launcher and Forge artifacts pass clean-install smoke tests.
- [ ] This authoritative set is reviewed and generated-contract drift is blocked.
- [ ] Phase roadmap completion claims match retained verification evidence.

## Product release condition

Release only when every unchecked item above is complete or explicitly removed
from the target product through a new documented product decision. Source code
presence, mock tests, and unrecorded manual success are not release evidence.
