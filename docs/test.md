# StoryTeller Target Test and Acceptance Strategy

## Scope

This document defines the tests required by the target product. It does not
claim they exist. Evidence-backed phase roadmap checkboxes record delivery state.

## Current codebase test audit

Audit snapshot: 2026-08-04. This snapshot is evidence for planning, not a durable
test-count promise.

| Area | Observed baseline | Rewrite assessment |
|---|---|---|
| Python | 849 tests collected from 50 `tests/test_*.py` files | Broad legacy v1 coverage for interfaces, pipeline, validation, checkpoints, packaging, generation steps, hardening, and early world generation |
| Android | 4 JVM unit-test files and 2 legacy `.story` fixtures | Covers graph, repository, save, and GM-index foundations; no v2 shared corpus or device/instrumentation evidence |
| iOS | 4 Swift unit-test files | Covers the same foundation areas; no v2 shared corpus, UI, physical-device, or native-model evidence |
| Real models | Marked Python smoke/integration tests | Useful baseline, but not a full real-model v2 generation and cross-platform import record |
| Procedural world | One substantial legacy Python test module | Useful algorithms and invariants exist, but not the complete Phase 2–4 physical/history/reconciliation contract |

The collected count alone does not establish correctness. Existing tests primarily
lock the code that the rewrite plans to reorganize or replace. They should be
retained only where behavior remains authoritative and rewritten around typed v2
contracts as each phase lands.

The audit run of `.venv/bin/pytest -q` produced **846 passed, 3 failed, and 81
warnings**. All three failures were real-model smoke tests attempting to load
`Qwen2.5-7B-Instruct-Q4_K_M.gguf` from the legacy `~/.storyteller/models` path.
This confirms that provisioned model tests currently leak into the default suite.
Most warnings are the marker-registration defect described below; configuration
tests also expose legacy behavior that ignores unknown model fields, which conflicts
with the target strict-configuration contract.

### Immediate baseline repairs

- Move pytest `markers` configuration out of `[tool.coverage.report]` and into
  `[tool.pytest.ini_options]`. The current placement causes unknown-marker warnings
  for `integration` and `slow` and prevents reliable gate selection.
- Add and enforce markers for `unit`, `contract`, `integration`, `real_model`,
  `determinism`, `security`, `performance`, and `release`; reject unknown markers.
- Split “requires installed local model” from ordinary integration tests. A default
  developer run must not accidentally invoke model inference, while a release gate
  must fail—not skip—when provisioned models are absent.
- Replace volatile test-count claims with a generated inventory containing commit,
  command, platform, collected/passed/failed/skipped counts, duration, and marker.
- Remove broad mypy test exemptions as contracts become typed. Target tests are
  part of the strict type gate, not an untyped exception to it.
- Add coverage measurement by domain and critical branch. A percentage alone is
  insufficient: every validation error, retry/abort decision, durable boundary,
  and security rejection requires a direct test.
- Introduce deterministic fixture builders. Canonical v2 fixtures are generated
  from frozen schemas and checked byte-for-byte into the shared corpus. v1
  rejection tests construct only the minimal unsupported-version input in memory;
  no v1 schema or fixture remains after Phase 6.
- Add mutation testing for validators, reconciliation, package acceptance, reveal
  filtering, and save binding. Surviving mutations in these boundaries block the
  phase that owns them.
- Make test isolation explicit: temporary roots per test, no writes to repository
  source/config/model directories, no network by default, fixed locale/timezone,
  and cleanup assertions for processes, model contexts, and temporary files.

## Test architecture

Target tests are organized by evidence level rather than by old implementation
phase names:

```text
tests/
  unit/             pure domain, typed configuration, prompt, diagnostic tests
  property/         generated small worlds and invariant tests
  contract/         schemas, ports, events, errors, package/save/GM contracts
  integration/      pipeline, repositories, backends with deterministic fakes
  crash/            fault injection at persistence boundaries
  determinism/      golden vectors and first-difference tooling
  security/         hostile archives, JSON, paths, models, privacy and fuzzing
  real_model/       explicitly provisioned desktop model tests
  performance/      named hardware/model profiles
  fixtures/v2/      shared bytes plus scenario catalog for Python/Android/iOS
```

Native suites mirror the shared scenario IDs. Every shared package case has one
expected acceptance result, stable diagnostic code, and where applicable graph,
save, media, and reveal expectations. Platform-specific UI and lifecycle tests
augment rather than redefine these contracts.

## Quality gates

| Gate | Models | Frequency | Blocks |
|---|---|---|---|
| Static/unit | none | every change | merge |
| Contract/integration | fakes + fixtures | every change | merge |
| Cross-platform package | canonical v2 fixtures | every change | merge |
| Real-model smoke | provisioned local models | scheduled/release | release |
| Full generation | all release models | release candidate | release |
| Physical mobile | downloaded GM model | release candidate | store submission |
| Compliance/manual quality | human review | release candidate | store submission |

Tests must never report a provisioned model absence as a product regression.
Model tests use an explicit marker and a precise skip/setup message locally;
release CI treats missing provisioned assets as infrastructure failure.

## Static gate

- Strict mypy across `src`, `scripts`, and tests
- Python lint/format checks
- Kotlin and Swift compiler/static analysis
- JSON Schema validation
- Broken Markdown-link and generated-contract drift checks
- Dependency/license inventory
- No secrets, models, build outputs, or saves committed

## Procedural unit tests

Each domain is tested separately with tiny deterministic grids:

- Domain-separated seed stability and collision checks
- Elevation range, configured land/continent constraints
- Hydrology downhill flow, basin/lake validity, river continuity, coast validity
- Climate range, latitude/elevation/orographic effects, season/weather validity
- Complete biome assignment and valid resource compatibility
- Region connectivity, adjacency symmetry, route endpoint/traversability rules
- Site coordinates and containment
- Civilization territory, population, government, economy, and route references
- History causal ordering, participant/location validity, consequences applied
- Snapshot/ledger consistency
- Serialization round-trip and stable canonical hash

Property tests should generate many small worlds and assert invariants rather
than expected names. Golden tests are limited to algorithm-version fixtures.

## Procedural determinism matrix

For each supported algorithm version:

| Variation | Expected result |
|---|---|
| Same specification, repeated | Identical domain bytes |
| Worker count 1 vs N | Identical domain bytes |
| Different output directory | Identical canonical bytes |
| Different master seed | Different world ID |
| Changed history years | Physical domains reused; history/downstream invalidated |
| Changed metres per world cell | Scale-dependent routes/downstream invalidated |
| Supported OS/Python | Identical deterministic procedural domains |

Procedural algorithms must be cross-platform deterministic; the weaker
same-machine guarantee applies only to model inference output.

## Reconciliation tests

Fixtures inject one contradiction at a time:

- Unknown major region/civilization
- Incorrect containment or coordinates
- Impossible route or non-neighbor border
- Climate/biome/resource contradiction
- Territory/government mismatch
- Event before its cause or after present year
- Dead participant acting after death without an explicit world rule
- Local entity without containing site/region
- Valid narrative-local building/ruin/minor character

Every invalid case produces a stable code and JSON path. The test confirms the
procedural input is byte-identical before and after retry.

## Pipeline unit and integration tests

- Plan dependency/acyclic/resource validation
- Typed artifact repository boundaries
- Model load/unload and RAM-budget enforcement
- Retry count (`max_retries` means retries after first attempt)
- Terminal configuration/resource/persistence errors are never retried
- Checkpoint save/load and internal checkpoint-schema upgrade behavior
- Event sequence, schema, and stable error fields
- Cancellation cleanup and no partial publication
- Application-service full run with tracked fakes
- CLI and future GUI invoke the same application path
- Prompt registry identity/version/hash resolution and immutable-version policy
- Typed prompt input rejection, deterministic rendering, and output-schema binding
- Configuration precedence, unknown-key rejection, canonical effective output,
  model/prompt checksum resolution, and GUI/CLI `RunSpec` equality
- Every emitted diagnostic exists in the typed catalog and has tested severity,
  retry, redaction, localization, and recovery semantics

## Crash and resume matrix

Inject process failure at both sides of every durable boundary:

```text
temporary write | fsync | rename | checkpoint commit | downstream start
```

Repeat for world domains, history batches, Bible, chapters, graph nodes, PNG,
thumbnail, MIDI, GM index, manifest, and final package. Resume must either reuse
a verified artifact or regenerate it; it must never trust stale checkpoints or
partial files.

Additional cases:

- File missing but checkpoint present
- File hash mismatch
- Producer fingerprint mismatch
- Dependency ID mismatch
- Database missing/corrupt
- Cancellation during model load and chunk generation
- Worker counts 1 and N
- Interrupted result equals uninterrupted canonical result

## Narrative contract tests

Tests validate structure and constraints, not exact model prose:

- Bible schema and all world references
- Story chapter/scene structure and entity continuity
- Graph reachability, choices, flags, conditional text, endings
- Every narrative major fact passes reconciliation
- Mature content profile is applied while prohibited content is blocked
- Prompt/model/schema provenance is present per artifact
- Long-step sub-checkpoints invalidate only when dependencies change

## Mandatory media tests

For every node:

- Image and thumbnail paths are declared and unique
- PNG signature and full decode succeed
- Full and thumbnail dimensions match manifest policy
- World and per-region maps decode, use authoritative geometry, and cover every
  declared region
- Thumbnail derives from accepted source image
- Structured score schema, rational timing, tempo/time/key maps, instrument roles,
  musical events, loop/intro/outro markers, provenance, and expected MIDI hash pass
- Non-reduced, zero-denominator, or non-960-representable positions are rejected;
  independent conforming renderers produce byte-identical MIDI
- MIDI header and complete parse succeed
- MIDI is SMF Type 1 at 960 PPQ, contains only the allowed General MIDI 1 subset,
  uses no proprietary SysEx, agrees with the score, contains sounding events, and
  has positive duration
- Hash, artifact ID, dependency IDs, and producer fingerprint match

No “partial but accepted” fixture exists. A single missing/invalid node asset
must prevent publication.

## Package v2 acceptance corpus

Canonical fixtures include:

- Minimal valid v2
- Representative complete one-continent v2
- Large valid world with full ledger
- Unsupported v1
- Missing/duplicate manifest
- Absolute path, traversal, symlink, duplicate ZIP path
- RFC 8785 canonicalization and JSON Schema Draft 2020-12 conformance vectors
- Malformed/noncanonical IDs, shortened SHA-256 values, and ID collisions
- Artifact-ID, content-hash, story-ID, and external package-hash golden vectors;
  changes to provenance/dependencies invalidate the appropriate identity
- Unsorted/duplicate feature arrays, unknown-required rejection, and
  unknown-optional tolerance
- Very large valid declared packages are not rejected by an arbitrary total-size
  ceiling; insufficient storage and structural-amplification attacks are rejected
- Excessive entry count/decompressed size
- Missing/undeclared domain
- Invalid JSON/schema/version
- Bad content or artifact hash
- Broken provenance/dependency cycle
- Invalid coordinate/reference/event cause
- Missing node image/thumbnail/score/MIDI
- Corrupt/wrong-size PNG, invalid score, score/MIDI mismatch, wrong SMF/PPQ,
  malformed loop markers, and corrupt/zero-duration MIDI
- Save data or executable content embedded in package

Python, Android, and iOS consume the same fixture bytes and a shared scenario
catalog. They must return the same conceptual acceptance/error codes.

## Player behavior scenarios

The shared catalog specifies expected entry node, node count, choices, flags,
endings, asset paths, package version, and rejection codes. Both platforms test:

- Staged import and atomic publication
- v1 rejection with regenerate-v2 guidance
- Read-only content
- Local save creation and atomic update
- Save/package hash mismatch isolation
- Choice/flag/conditional text behavior
- Image rendering and MIDI looping/crossfade
- App restart restoration
- Story deletion with explicit save/history choice
- No network attempt after model installation

## Strict spoiler tests

Use a fixture whose unrevealed secret contains a unique sentinel phrase.

1. Query before its reveal node: sentinel source ID and text must be absent from
   candidates, assembled prompt, streamed output test double, and logs.
2. Visit the reveal node and repeat: the entry becomes eligible.
3. Test branches where the node is never visited.
4. Test conversation history cannot reintroduce unrevealed knowledge.
5. Compare eligible entry ID sets across Python reference logic, Android, iOS.

Prompt instructions alone do not satisfy these tests.

## GM streaming tests

- First-launch download resume, cancellation, bad checksum, insufficient space,
  atomic install, deletion, and offline restart
- Ordered non-empty chunks and one completion
- UI responsiveness and backpressure
- Cancellation releases native context and does not persist an unmarked partial
  assistant message
- Completed exchanges persist across restart
- History clearing is local and complete
- Time to first chunk, tokens/second, peak RAM, and thermal behavior on devices
- No network access during inference

## Launcher tests

- Argument vector preserves spaces and rejects shell injection
- Human form maps to exact CLI options
- Unknown JSONL events are ignored safely
- Sequence gaps/invalid event produce diagnostics without corrupting run state
- Cancel/resume use supported process behavior
- Final package path opens/reveals correctly
- Packaged launch on Windows, native Linux/macOS, and Wine

## Determinism tests

Canonical comparison strips or excludes only explicitly operational data. Tests
compare entry inventory and bytes and print the first path/JSON pointer mismatch.

- Pure procedural output: cross-platform bit identity
- Fake-backed full package: archive bit identity
- Real-model output: same-machine/profile identity
- Different output directories: identity
- Worker count variation: identity
- Resume vs uninterrupted: identity
- ZIP ordering, timestamp, permissions, and compression settings: identity

## Performance and resource targets

Thresholds are established from representative hardware after the Phase 6 v2
schema freeze and before release, then recorded per profile. Required
measurements:

- Each procedural domain and years simulated/second
- World peak memory by grid size
- Each model load/unload time and resident memory
- Full generation wall time and peak RAM
- Per-node image and score/MIDI throughput
- Package size and import time (measured, not capped)
- Player idle/reading/GM peak RAM
- First GM chunk latency and sustained generation rate
- Battery/thermal behavior for a representative GM conversation

Regression budgets use percent change against a versioned baseline rather than
invented universal hardware limits.

## Security tests

- ZIP/path/decompression attacks
- Malicious JSON depth/size and duplicate identifiers
- Integer/float extremes and non-finite values
- Model download redirect/source/checksum failures
- Package cannot deliver executable code or a model
- Imported content cannot escape read-only storage
- Save and GM history stay app-private
- Logs/events do not contain full questions, conversations, or hidden lore
- Offline test blocks network and exercises all post-download features

## Compliance tests

- AI and mature-content disclosure visible
- Privacy/support/license/notice screens accessible
- No analytics or advertising SDK
- Platform manifests request only necessary permissions
- User can flag GM output locally and export only by explicit action
- User can delete downloaded model and all story-local data
- Store declarations match observed data flow

## Human quality review

Release worlds are reviewed for geographical plausibility, historical causality,
Bible reconciliation, narrative quality, meaningful branches, image continuity,
music fit/looping, GM character/accuracy, spoiler isolation, and prohibited
content. Human review supplements automated acceptance; it does not replace it.

Use a versioned scorecard with anchored examples. Require at least two independent
reviewers for release candidates and record disagreements/resolution. Reviewers
must assess representative branches and unrevealed GM questions, not only the
happy path. Human notes contain no private paths, prompts, or unnecessary model
conversation logs.

## Accessibility and UX tests

- Forge launcher completes configure, validate, generate, cancel, resume, and open
  output using keyboard-only and screen-reader paths.
- Android TalkBack and iOS VoiceOver traverse library, import, reader, choices,
  ending, model setup, errors, and GM chunks in logical order.
- Dynamic Type/font scaling and reflow do not hide narrative, choice, progress, or
  recovery controls.
- Contrast, reduced motion, non-color status, touch targets, focus restoration,
  and progress announcements satisfy `accessibility.md`.
- Images expose package-provided alternatives; meaningful MIDI information has a
  text equivalent and reading works with audio disabled.
- Package removal and save deletion remain separate and unambiguous.
- Localization pseudo-locale tests detect clipping, concatenation, and untranslated
  stable-diagnostic fallbacks.

## Prompt, configuration, and diagnostic contract tests

The four supporting target documents add test obligations that are release
contracts, not optional documentation checks:

- Prompt registry entries resolve to immutable files and output schemas; hashes
  match bytes; golden rendering is cross-platform stable; resume invalidation
  follows prompt dependency changes; unrevealed GM sentinels never enter prompts.
- Configuration defaults produce the one-continent mandatory flow; precedence is
  deterministic; equivalent YAML/CLI/GUI inputs yield identical `RunSpec`; unsafe
  resources, paths, missing models, and checksum changes fail before generation.
- Every `ST-*` code has unique immutable meaning, typed metadata, appropriate UI
  mappings, redacted details, and a tested recovery path. Known errors may not fall
  through to `ST-INTERNAL-001`.
- Generated configuration, CLI, diagnostic, prompt-registry, schema, and package
  references fail CI when they drift from executable definitions.

## Rewrite roadmap traceability

This matrix is normative: a roadmap phase cannot complete unless every listed
test family exists, passes at the appropriate gate, and is referenced by stable
test/scenario IDs in that phase's evidence record.

| Rewrite phase | Corresponding required tests in this document |
|---|---|
| **Phase 1 — Contracts and foundations** | `RunSpec`/`WorldSpec` parse, serialization, ranges, preflight, and precedence; unknown-key failure; fixed-point overflow/rounding; SHA-256 domain seed, SplitMix64, stable-ID and embedded reference-generator golden vectors; typed repository/envelope round trips; canonical JSON/grid chunks; atomic crash windows; plan dependency/cycle/resource/hash invalidation; worker-order independence; exact retry/terminal semantics; diagnostic/event stability; cancellation; prompt registry; all entry points using one application service; architecture ban on new legacy-worldgen imports |
| **Phase 2 — Authoritative physical world** | Grid coverage/bounds; spaced plates, ownership and boundary symmetry; exact one/multiple continent counts; elevation and erosion mass conservation; geology/strata/deposit compatibility; hand-calculated priority flood, watersheds, basin/lake outlets, river termination and tributary acyclicity; four-season climate range, lapse, coastal moderation, wind/moisture/rain-shadow bounds; total soil/biome classification; renewable resource, species, food-web, migration and carrying-capacity invariants; complete region ownership/connectivity/adjacency; stable seasonal routes/capacity; map source/label and index rebuild equality; worker/order/platform byte identity |
| **Phase 3 — Civilizations and history** | Builtin registry validation/hashes and balanced recipes; language/name grammar vectors, collisions, flags/scripts; objective magic costs/prohibitions and true/false/uncertain beliefs; culture/government/succession constraints; site suitability/separation/containment; initial cohort/stockpile/territory conservation; monthly births/deaths/migration/disease/harvest/production/spoilage/consumption/depletion/trade/prices; supplied diplomacy/war/peace/occupation transitions; causal event ordering/references; exactly-once changes; population/migrant/army/goods/currency/deposit conservation; collection-order independence; atomic batches; ledger-prefix and genesis/snapshot replay equality; full ledger retained despite summary omission |
| **Phase 4 — Bible and reconciliation** | Typed full-domain world queries; deterministic projection, complete source coverage, and budgeted chunking; removal of direct prose adapter from production; permitted contained local entities; unknown authoritative entity rejection; route, climate, biome, resource, territory, government, person, magic-law, belief-status, event-cause/year, present-year, and dead-participant contradictions; immutable procedural bytes/dependency hashes across every retry; optional critic failure; reconciliation report hashes, stable codes and JSON paths |
| **Phase 5 — Narrative, media, local worlds, GM knowledge** | Opportunity reference/reachability/no-new-fact and deterministic scoring; story/graph world references, route feasibility, topology, flags, conditional text and endings; all-site local strata/cave/aquifer/river/coast/road/building/event-scar reconciliation; legal vertical paths; fluid/heat conservation; support/collapse and site-stream/resume determinism; per-node seeds/worker identity; media crash windows, fixed PNG profiles, authoritative structured score, SMF Type 1/960 PPQ derivative agreement and MIDI acceptance; mandatory coverage; complete global/local/opportunity GM index source and incoming/outgoing reference coverage; visited-node sentinel filtering before prompt assembly |
| **Phase 6 — Persistence and v2 freeze** | Valid/invalid fixture for every frozen worldgen and product schema; canonical JSON/chunk/path/unit/ID/hash vectors; complete procedural inventory including unused facts; provenance DAG completeness/cycles/broken IDs; domain/chunk hash recomputation; history replay and index rebuild during acceptance; macro/local reconciliation; atomic JSON/media/package crash matrix; resume mismatches; traversal, symlink, duplicate/bomb limits; incomplete world, corrupt chunk, broken causal link/index rejection; v1 rejection/no migration; canonical archive equivalence and informative first difference |
| **Phase 7 — Android and iOS Players** | Shared v2 corpus including small/representative/large chunked worlds, full ledgers and local maps; bounded lazy readers; native integer/unit/ID/path/chunk-hash/reference parity; missing chunks, broken causes/indexes and package/save world-hash rejection; safe staging/no partial import; immutable full-data retention; local atomic saves; identical graph/flag/ending/media behavior; library deletion separation; accessibility; network-blocked no-cloud/telemetry proof |
| **Phase 8 — Local GM and thin GUI** | Download resume/cancel/checksum/space/atomic-install/offline restart; native lifecycle; complete lazy global/history/local-map retrieval; cross-platform candidate/source/reveal ID and scoring equality using nodes, routes, sites, people, events, beliefs and opportunities; unrevealed global/local sentinels absent from prompt/log/chunks/history; semantic chunk ordering/backpressure/persistence/cancellation; launcher full-`WorldSpec`/CLI equality, argv safety, event/cancel/resume/final path, Wine/native launch, and proof of no GUI generation implementation |
| **Phase 9 — Hardening and release** | Legacy worldgen import/schema/mode/fallback and canonical-float absence scans; worldgen property/mutation/fuzz/crash/resume/security/performance/memory gates; fixed-point cross-platform/worker/path/iteration/resume identity and first differences; full default 500-year resource/replay evidence; full-data retention audit; complete real-model v2 run through Bible, reconciliation, narrative, local maps/media, package, physical Android/iOS import and GM retrieval; all broader provisioned/platform/compliance/accessibility/packaging gates and generated-document drift checks |

### Phase evidence format

Each completed phase stores a machine-readable record containing:

```yaml
phase: 1
git_commit: "<sha>"
commands: ["<exact command>"]
tests:
  collected: 0
  passed: 0
  failed: 0
  skipped: 0
scenario_ids: ["P1-CONFIG-001", "P1-SEED-001"]
platforms: ["<os/runtime profile>"]
fixtures_sha256: "<sha256>"
```

Skipped tests require a recorded reason and cannot satisfy a phase exit condition.
Phase 7–9 physical, real-model, security, compliance, accessibility, or packaging
evidence cannot be substituted with fakes.

## Recommended commands

```bash
.venv/bin/mypy src scripts tests
.venv/bin/pytest -q -m "not integration"
.venv/bin/pytest -q -m determinism
.venv/bin/pytest -q tests/test_story_fixtures.py
```

Provisioned acceptance:

```bash
STORYTELLER_MODELS_DIR="$PWD/ai_models" \
  .venv/bin/pytest -q -m integration
```

Android and iOS commands must run the shared v2 scenario catalog in CI; exact
commands are generated from their build configuration once v2 adapters land.

## Release definition of done

- All static, unit, contract, cross-platform, security, and offline gates pass.
- A real-model v2 package is accepted and imported on physical Android and iOS.
- Interrupted and uninterrupted canonical results match.
- Every story node has valid required media.
- Strict spoiler sentinel tests pass on both Players.
- Local model download and chunk streaming meet recorded device budgets.
- Compliance evidence is dated and complete.
- Phase roadmap checkboxes accurately reflect retained verification evidence.
