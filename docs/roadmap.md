# StoryTeller — Development Roadmap

## Overview

Development is organized into 9 phases. Each phase produces a testable, demonstrable increment.

---

## Phase 0: Documentation

**Goal:** Complete design documentation before any code is written.

**Tasks:**
- [x] Write `goal.md` — application vision, principles, non-goals
- [x] Write `arch.md` — technical architecture, data schemas, coding patterns
- [x] Write `design.md` — behavioral design, pipeline flows, UX flows
- [x] Write `roadmap.md` — this file
- [x] Write `test.md` — test strategy for all phases
- [x] Write `readme.md` — usage guide for both apps
- [x] Write `api.md` — interface definitions, config spec, CLI reference
- [x] Write JSON schemas in `docs/schemas/` (bible, story, graph, manifest, gm_index, style_bible)
- [x] Cross-reference all documents

**Deliverable:** Complete documentation. Every design decision recorded. All schemas defined.

**Status:** ✅ Complete.

---

## Phase 0.5: Pre-Coding Artifacts

**Goal:** Create the concrete artifacts needed before any Python code is written. These are the bridge between documentation and implementation.

**Tasks:**
- [x] Write all 8 prompt templates in `forge/src/prompts/`
  - `world_builder_v1.j2` — generates structured World Bible from tone + title
  - `story_writer_v1.j2` — generates chapter text with Bible injection
  - `game_designer_v1.j2` — extracts decision points, builds graph skeleton, writes node text
  - `art_director_v1.j2` — generates image prompts with style bible suffix
  - `composer_v1.j2` — detects music tone, generates ABC notation
  - `game_master_v1.j2` — answers reader questions with injected context
  - `style_bible_v1.j2` — generates art style constraints from World Bible
  - `consistency_check_v1.j2` — LLM-based lore violation detection
- [x] Create `config/models.yaml` — interface→concrete model mapping
- [x] Create `forge/pyproject.toml` — dependencies, dev tools, project metadata
- [x] Create `.gitignore` — exclude models, venv, output, secrets
- [x] Create test fixtures in `forge/tests/fixtures/`
  - `bible_valid.json` / `bible_invalid.json`
  - `story_valid.json`
  - `graph_valid.json` / `graph_with_orphan.json` / `graph_with_cycle.json`
  - `gm_index_valid.json`
  - `manifest_valid.json`
  - `abc_valid.txt` / `abc_invalid.txt`
  - `style_bible_valid.json`
- [x] Validate all JSON schemas against fixtures — catch schema errors now
- [x] Scaffold `forge/src/` directory tree per `arch.md`
- [x] Initialize git repository
- [x] Create empty `mobile/`, `mac/`, `windows/` directories (mobile contains android/ + ios/)

**Deliverable:** Ready to write Python code. Project structure exists, prompts are versioned, schemas validate, fixtures enable TDD.

**Status:** ✅ Complete.

> ⚠️ **Development principle: build vertically first.** Before adding parallelism, retries, or optimization, prove the core pipeline end-to-end: generate one valid World Bible → one story → one graph → package one .story → load it on mobile. Only then expand horizontally. This gives early feedback and reduces over-engineering risk. Phases 1-5 should produce a working (slow, single-threaded) pipeline before Phase 2's Job Queue adds parallelism.

---

## Phase 1: Interfaces & Model Abstraction Layer

**Goal:** Define all interfaces (TextGenerator, Validator, ImageGenerator, MusicGenerator, GameMaster) and their concrete implementations.

**Tasks:**
- [x] Define `forge/src/interfaces/` — all 5 Protocol classes
- [x] Implement `forge/src/backends/llm_backend.py` — concrete TextGenerator + Validator
- [x] Implement `forge/src/backends/image_backend.py` — concrete ImageGenerator
- [x] Implement `forge/src/backends/midi_backend.py` — concrete MusicGenerator (real ABC→MIDI)
- [x] Implement `forge/src/backends/gm_backend.py` — concrete GameMaster stub
- [x] Implement `forge/src/backends/model_manager.py` — shared lifecycle + RAM budget
- [x] Implement `forge/src/config.py` — YAML loader, model resolution
- [x] Write unit tests for all interfaces and backends (166 tests)

**Deliverable:** Can load any configured model, generate text/images/MIDI through interfaces. Swapping models requires only config change.

**Status:** ✅ Complete. 166 tests (Phase 1), mypy strict: 0 errors.

---

## Phase 2: Pipeline Engine (Job Queue + Worker Pool)

**Goal:** The Generator → Validator → Normalizer → Commit pipeline with parallel execution.

**Tasks:**
- [x] Implement `forge/src/job_queue.py` — JobQueue dispatch layer (execute_step, execute_parallel, event log) delegating to PipelineStep.run()
- [x] Implement `forge/src/normalizer.py` — ID warnings, enums, flag names, sorting, JSON, whitespace, asset paths
- [x] Implement `forge/src/models/base.py` — PipelineStep with retry + feedback
- [x] Implement `forge/src/storage/checkpoint.py` — SQLite save/load/resume
- [x] Write unit tests for job queue, normalizer, checkpoint (32 additional tests)

**Deliverable:** Job Queue + Normalizer + Checkpoint system all working. Can run a dummy pipeline.

**Status:** ✅ Complete. Phase 1+2 cumulative, mypy strict: 0 errors.

---

## Phase 3: Schema & Validation Layer

**Goal:** All JSON schemas defined and validators working.

**Tasks:**
- [x] All 6 JSON Schema files in `docs/schemas/` — draft-07 validated
- [x] Implement `forge/src/validators/schema_validator.py` — loads schemas, validates, formats retry
- [x] Implement `forge/src/validators/cross_ref_checker.py` — entity IDs, node targets, flags, prefix matching
- [x] Implement `forge/src/validators/graph_validator.py` — reachability, orphans, dead ends, cycles
- [x] Integration tests chaining all 3 validators end-to-end
- [x] Write unit tests for all validators (44 tests)

**Deliverable:** Can validate any JSON against schemas and detect structural/graph issues. Full validation pipeline works end-to-end.

**Status:** ✅ Complete. Phase 1-3 cumulative, mypy strict: 0 errors.

---

## Phase 4: World Builder + Story Generation

**Goal:** Bible and linear story generation working.

**Prerequisites (done):**
- [x] Prompt: `world_builder_v1.j2`
- [x] Prompt: `story_writer_v1.j2`
- [x] Prompt: `style_bible_v1.j2`
- [x] Prompt: `consistency_check_v1.j2`
- [x] `forge/src/storage/checkpoint.py`
- [x] Test fixtures: `story_valid.json`, `story_invalid.json`, `style_bible_valid.json`, `style_bible_invalid.json`
- [x] `forge/src/models/base.py` (PipelineStep)

**Tasks:**
- [x] Implement `forge/src/models/world_builder.py` (subclass PipelineStep)
- [x] Implement `forge/src/models/art_director.py` (style bible)
- [x] Implement `forge/src/models/story_writer.py` (outline + 3 chapters)
- [x] Implement `forge/src/validators/consistency.py` (programmatic bible-violation checks)
- [x] Write unit tests: WorldBuilder (6), ArtDirector (7), StoryWriter (9), Consistency (10)
- [x] Integration test: Bible + style bible + story generation end-to-end
- [x] Test fixtures: story_valid.json passes, story_invalid.json fails, style_bible_invalid.json fails

**Deliverable:** `world_builder + art_director + story_writer + consistency` produce valid, consistent output.

**Status:** ✅ Complete. Phase 1-4 cumulative, mypy: 0 errors.

---

## Phase 5: CYOA Graph + Asset Generation

**Goal:** Complete App B pipeline — from Bible to .story package.

**Tasks:**
- [x] Implement `forge/src/models/game_designer.py`
  - Decision points extraction (prompt mode 1)
  - Graph skeleton generation (prompt mode 2)
  - Sequential node text generation (prompt mode 3) — one shared LLM instance
  - **Merge:** skeleton data (chapter, scene_type, present_characters, present_location) + Mode 3 text (text, choices, mood, image_prompt, music_tone) into complete nodes matching graph.schema.json
  - Consequence flag assignment
  - Conditional text generation
- [x] Implement `forge/src/models/image_generator_step.py` (parallel image generation)
- [x] Implement `forge/src/models/music_generator_step.py` (parallel MIDI generation)
- [x] Implement `forge/src/storage/indexer.py` (GM index)
- [x] Implement `forge/src/storage/packager.py` (deterministic .story ZIP)
  - Sorted JSON keys, fixed float precision, normalized timestamps
  - content/ and save/ directory structure
- [x] Implement `forge/src/storage/orchestrator.py`
  - Pipeline scheduler (sequential + parallel phases)
  - Checkpoint integration
  - Progress reporting
- [x] CLI entry point (`forge/src/cli.py` — 11 commands: generate, download-models, resume, config, verify, info, package, validate-story, validate-graph, validate-all, validate-bible)
- [x] Full integration test: Bible → .story end-to-end (`test_integration_pipeline.py` — 9 tests)
- [x] ArtifactStore: streaming write-through to disk (`artifact_store.py` + 24 tests)
- [x] Bible helpers: shared `_summarize_bible` formatter (`bible_helpers.py` + 18 tests)
- [x] CLI tests: all 11 commands parser coverage (`test_cli.py` — 20 tests)
- [x] Docker support: `Dockerfile`, `docker-compose.yml`, `run_docker.sh`
- [x] Model download: `pull_models.sh` downloads 4 GGUF models (12.3 GB)
- [x] Dry-run verification: `dry_run.py` (mock pipeline end-to-end)
- [x] Write-through verification: `verify_streaming.py`
- [x] Determinism test: same seed + same machine → identical output (verified with mocks)

**Deliverable:** Running `forge generate --seed 42` produces a complete, same-machine-reproducible .story file.

**Status:** ✅ Complete. 569 tests (all phases), mypy: 0 errors (src + scripts + tests).

**Estimated time:** 3-4 weeks (completed).

---

## Phase 5.6: Forge Hardening

**Goal:** Close the remaining gaps identified in the tmp/suggestions.md audit — fix finalization wiring, enforce run fingerprints, make resume work end-to-end, and bring the Forge to production-grade reliability.

**Source:** `tmp/suggestions.md` (2026-08-04), consolidated from all Markdown reports.

### A. Fix Finalization Wiring

- [ ] **A1:** Fix `package_path` lookup in `GenerateStory._build_result()` — read from `ctx.outputs["packager"]`, not `ctx.outputs["manifest"]`
- [ ] **A2:** Make `PackageAcceptance.validate()` unconditional — always runs, missing packager result is terminal
- [ ] **A3:** Supply schemas dir to `ManifestBuilder` so schema validation is mandatory, not best-effort
- [ ] **A4:** Manifest schema failure raises `PackageValidationError` (terminal), never a warning
- [ ] **A5:** Unify content hash algorithm between `ManifestBuilder` and `Packager` — one canonical implementation
- [ ] **A6:** Define `manifest_artifact_id` (hash of canonical content inventory) vs `package_hash` (ZIP bytes, sidecar only)

### B. Make Resume Work Through the Application Service

- [ ] **B1:** Route `GenerateStory.execute()` through `Orchestrator.run()` instead of manual `execute_step()` calls — one runner owns execution and checkpoint commits
- [ ] **B2:** Honor `request.resume=False` by clearing existing checkpoints; `resume=True` restores canonical artifacts before scheduling downstream work
- [ ] **B3:** Save checkpoints after every text phase (not just component-level)
- [ ] **B4:** Checkpoint GM index, manifest, and package result
- [ ] **B5:** Add resume test that invokes `GenerateStory`, not isolated orchestrator

### C. Enforce Run Fingerprints

- [ ] **C1:** Populate `run_fingerprint` on every checkpoint save (seed, title, tone, config hash, model file hashes, prompt hashes, schema versions, pipeline version)
- [ ] **C2:** Before reusing a checkpoint, compare fingerprint — refuse unsafe resume or invalidate downstream artifacts
- [ ] **C3:** Start with whole-run exact matching; dependency-level invalidation can follow later

### D. Finish Reproducibility Semantics

- [x] **D1:** Separate canonical from operational metadata — done (Phase 5.5E: `meta` sub-object in manifest)
- [ ] **D2:** Remove `time.time()` from `run_id` generation — use `{seed}_{fingerprint[:8]}`
- [ ] **D3:** Add production-assembly test: fake-backed service twice in different directories → identical archive SHA256
- [x] **D4:** Content-derived artifact IDs (no timestamps) — done (Phase 5.5E)

### E. LLM Validator Connection Policy

- [ ] **E1:** Register validator model with `ModelManager` under `ModelRole.VALIDATOR`
- [ ] **E2:** Document policy: deterministic validation mandatory, LLM critique optional (flag-gated)
- [ ] **E3:** Never allow validator exception to silently become "valid" — distinguish skipped/unavailable/failed/valid/invalid
- [ ] **E4:** Make validator seed and sampling deterministic

### F. Configuration-Driven Provider Factories

- [ ] **F1:** Add provider registry (`TEXT_PROVIDERS`, `IMAGE_PROVIDERS` dicts) — `provider` field selects adapter dynamically
- [ ] **F2:** Unknown provider → `ConfigurationError` (not silent stub fallback)
- [ ] **F3:** Strict config parsing: reject unknown keys, validate positive worker/retry/RAM values, require `repo`/`file` by provider
- [ ] **F4:** Add image-specific config fields (`size`, `steps`)
- [ ] **F5:** Resolve paths relative to config file, not CWD

### G. Apply All Configured Policies

- [ ] **G1:** `PipelineConfig.max_retries` replaces `PipelineStep.MAX_RETRIES` (config-driven)
- [ ] **G2:** `checkpoint_interval` controls how often checkpoints are saved
- [ ] **G3:** Global `failure_policy` is single source for execution behavior
- [ ] **G4:** `model_unload_threshold` used by resource scheduling
- [ ] **G5:** Create immutable `ExecutionPolicy` dataclass from config, pass to runner

### H. Declarative Pipeline Plan

- [ ] **H1:** Add lightweight `StepSpec` dataclass: `id`, `output`, `requires`, `model_roles`, `validation`, `failure_policy`, `checkpoint_policy`
- [ ] **H2:** Validate plan before loading models: every requirement has one producer, outputs unique, deps acyclic, concurrent steps fit resource plan
- [ ] **H3:** Drive `GenerateStory` execution from plan; retire hard-coded `Orchestrator.run()` once stable
- [ ] **H4:** Use same plan for execution, resume, progress reporting, tests, docs

### I. Strengthen Package Acceptance

- [ ] **I1:** Always validate all contained JSON against schemas
- [ ] **I2:** Recompute and compare canonical content hash
- [ ] **I3:** Require non-empty manifest artifact/story IDs
- [ ] **I4:** Verify manifest inventory against actual archive entries
- [ ] **I5:** Validate graph references to every required media asset
- [ ] **I6:** Reject undeclared files by extension policy
- [ ] **I7:** Enforce supported package/schema versions
- [ ] **I8:** Add `forge validate-package` CLI command (same acceptance rules as production)

### J. Complete Event Integration

- [ ] **J1:** Pass real `run_id` through every typed event
- [ ] **J2:** Emit model lifecycle, validation failures, retries, quarantine, checkpoint saves, pipeline completion
- [ ] **J3:** Add `EventSink` protocol — JSONL adapter + in-memory sink for tests
- [ ] **J4:** `GenerateStory` configures event-log path consistently

### K. Cancellation-Safe Cleanup

- [ ] **K1:** Handle `asyncio.CancelledError` and SIGINT gracefully
- [ ] **K2:** Stop scheduling new node jobs on cancel; wait for or cancel active jobs
- [ ] **K3:** Do not publish partially written files
- [ ] **K4:** Save latest consistent checkpoints before exit
- [ ] **K5:** Unload all models on cancel
- [ ] **K6:** Emit cancellation/failure event; return distinct CLI exit status

### L. Split Long Text Operations

- [ ] **L1:** StoryWriter: add checkpoints for outline, each chapter, consistency pass
- [ ] **L2:** GameDesigner: add checkpoints for decision points, graph skeleton, each node's text
- [ ] **L3:** Each sub-artifact carries dependency hashes — changed upstream invalidates downstream

### M. Finish Mypy + Cross-Platform Fixtures + Docs

- [ ] **M1:** Fix 2 remaining mypy errors in `scripts/generate_story_fixtures.py`
- [ ] **M2:** Strict mypy: 0 errors across `src`, `scripts`, `tests`
- [ ] **M3:** Share canonical `.story` fixtures between Forge, Android, and iOS tests
- [ ] **M4:** Update documentation to reflect current architecture: `GenerateStory` service, bounded batch scheduling, manifest/meta split, actual resume support, current test count (602)

### N. Type Composition Boundaries

**Source:** `tmp/suggestions2.md` §1 — composition relies on `dict[str, Any]`, string keys, non-generic `StepOutput`.

- [ ] **N1:** Add `ArtifactKey` as a `Literal` or enum for all canonical artifacts
- [ ] **N2:** Make `StepOutput[T]` generic
- [ ] **N3:** Add TypedDict/Pydantic boundary models for Manifest, GraphNode, Choice, image metadata, and MIDI metadata
- [ ] **N4:** Replace title/tone/temperature lookups in `PipelineContext.state` with a typed run request/specification
- [ ] **N5:** Add typed artifact repository methods for high-value artifacts (`get_bible()`, `put_graph()`, etc.)

### O. Atomic Persistence and Recovery

**Source:** `tmp/suggestions2.md` §2 — crash can leave artifact without checkpoint or checkpoint inconsistent with disk.

- [x] **O1:** Write JSON outputs to temporary files in the target directory — done (Phase 5.5E: ArtifactStore atomic writes)
- [ ] **O2:** Write image/MIDI media outputs to temporary paths, atomically rename into place after successful generation
- [ ] **O3:** Store artifact content hash and canonical path in checkpoint metadata
- [ ] **O4:** On resume, reconcile checkpoint hash with actual disk artifact — skip or re-generate on mismatch
- [x] **O5:** Write final `.story` to a temporary path and publish it only after PackageAcceptance passes — done (Phase 5.5E: Packager atomic rename)
- [ ] **O6:** Add crash-window tests for artifact-before-checkpoint and checkpoint-before-artifact failures

### P. Per-Node Asset Checkpoints

**Source:** `tmp/suggestions2.md` §3 — `GenerateStory` stores aggregated batch result only after entire batch returns.

- [x] **P1:** Add `BatchScheduler` checkpoint_store integration — done (Phase 5.5H item 3)
- [x] **P2:** Commit/checkpoint every successful image immediately — done (per-node checkpoint on each success)
- [x] **P3:** Commit/checkpoint every successful MIDI track immediately — done
- [ ] **P4:** Persist structured quarantine records with stable error codes (not just string messages)
- [ ] **P5:** Resume schedules only missing, invalid, or fingerprint-mismatched node assets
- [ ] **P6:** Add per-node retry limits driven by `ExecutionPolicy`
- [ ] **P7:** Verify identical asset outputs with worker counts 1 and N

### Q. Asset Coverage Policy

**Source:** `tmp/suggestions2.md` §4 — structurally valid package may have incomplete scene media.

- [ ] **Q1:** Define whether illustrations and MIDI are required, optional, or threshold-based
- [ ] **Q2:** Add configurable minimum coverage (e.g., 100% images, 80% MIDI)
- [ ] **Q3:** Record quarantined/missing assets explicitly in manifest stats
- [ ] **Q4:** `PackageAcceptance` enforces the configured coverage policy
- [ ] **Q5:** CLI result reports incomplete-but-accepted versus fully complete packages distinctly

### R. Binary Asset Acceptance

**Source:** `tmp/suggestions2.md` §5 — existing file path is insufficient evidence of usability.

- [ ] **R1:** Decode every packaged PNG and reject corrupt images
- [ ] **R2:** Verify full images and thumbnails have the configured dimensions
- [ ] **R3:** Parse every MIDI and reject corrupt/empty tracks
- [ ] **R4:** Verify MIDI duration is greater than zero
- [ ] **R5:** Add corrupt PNG and MIDI archive fixtures

### W. Policy Semantics Tests

**Source:** `tmp/suggestions2.md` §11 — retry/failure semantics not explicitly locked by tests.

- [ ] **W1:** Define whether `max_retries` excludes or includes the first attempt
- [ ] **W2:** Verify terminal configuration/resource/persistence errors are never retried
- [ ] **W3:** Verify validation/generation errors retry exactly according to policy
- [ ] **W4:** Verify QUARANTINE applies only to independent item jobs
- [ ] **W5:** Verify phase dependencies and storage failures always abort

### X. Artifact Provenance

**Source:** `tmp/suggestions2.md` §12 — run fingerprint answers "does this run match?" but not "why does this artifact exist?"

- [ ] **X1:** Add canonical artifact IDs inside artifact envelopes or manifest inventory
- [ ] **X2:** Record `depends_on` relationships: Bible → Story → Graph → Assets/Index → Package
- [ ] **X3:** Record model and prompt hashes per producing artifact, not only globally
- [ ] **X4:** Use dependency IDs in cache/resume invalidation
- [ ] **X5:** Add provenance consistency checks to `PackageAcceptance`

### Definition of Done for Phase 5.6

- `forge generate` produces schema-valid, accepted `.story` or exits non-zero
- Package acceptance always runs through the application service
- Manifest identity, inventory, and hashes are complete and verified
- `resume` works through `GenerateStory`, not only isolated orchestrator tests
- Unsafe checkpoints rejected by run fingerprints
- Interrupted and uninterrupted runs produce identical canonical results
- All configured execution policies affect runtime behavior
- Strict mypy: 0 errors across `src`, `scripts`, `tests`
- One real-model end-to-end run recorded
- Android and iOS accept the same canonical package fixture
- Documentation distinguishes verified behavior from future work

**Source:** `tmp/suggestions.md` + `tmp/suggestions2.md` (2026-08-04).

**Status:** 🔴 Not started. 19 sections (A–X), ~80 actionable tasks.

**Estimated time:** 4-6 weeks.

---

## Phase 6: Mobile Player (App A)

**Goal:** iOS and Android apps that read .story files.

### Android (Kotlin + Jetpack Compose)

- [x] Project setup with Gradle, Compose, llama.cpp JNI (wrapper config + setup script)
- [x] .story import: file picker, ZIP extraction, content/save split
- [x] Book reader: page rendering, choice buttons, image display
- [x] MIDI player: Sonivox EAS, looping, crossfade
- [x] Game Master: llama.cpp integration, gm_index retrieval, streaming
- [x] State management: flags, conditional text, ending detection
- [x] Save state persistence (save/ JSON)
- [x] Library screen with import/delete
- [x] Unit tests: GmIndex (10), SaveState (10), GraphNode (6)
- [ ] Native compilation: gradlew build, llama.cpp JNI (requires Android Studio / NDK)

### iOS (Swift + SwiftUI)

- [x] Project setup with Xcode, SwiftUI, llama.cpp C API bridging header (xcodegen project.yml)
- [x] .story import: document picker, content/save split
- [x] Book reader: SwiftUI views, AsyncImage
- [x] MIDI player: AVAudioEngine, looping, crossfade
- [x] Game Master: llama.cpp, gm_index retrieval, chat streaming
- [x] State management + save persistence (JSON)
- [x] Unit tests: GmIndex (9), SaveState (9), GraphNode (6)
- [ ] Native compilation: Xcode build, llama.cpp Swift bindings (requires Xcode + build_llama.sh)

### Cross-Platform Contract Scenarios (Phase 5.6 overflow)

**Source:** `tmp/suggestions2.md` §6–8.

- [ ] **S1:** Define shared scenario IDs and expected outcomes for canonical fixtures (entry point, node count, choices, flags, endings, media paths)
- [ ] **S2:** Verify invalid packages (path traversal, missing manifest, bad graph ref, hash mismatch) are rejected identically on all platforms
- [ ] **S3:** Verify `reveal_after_node` produces identical spoiler gating on Forge test logic, Android, and iOS
- [ ] **S4:** Add fixture version/update tooling so platform copies cannot drift silently
- [ ] **T1:** Android distinguishes supported, older-migratable, newer-unsupported, and corrupt packages
- [ ] **T2:** iOS implements the same version outcomes and user-facing messages
- [ ] **T3:** Add shared unsupported-version and migration fixtures; keep reader save state outside immutable imported content
- [ ] **Game Master:** Implement token callbacks/streaming, or document GM output as asynchronous non-streaming
- [ ] **Game Master:** Add package-to-reader tests for `reveal_after_node` filtering
- [ ] **Game Master:** Test GM model download integrity, partial-download recovery, and offline restart
- [ ] **Game Master:** Measure time-to-first-token and peak RAM on physical Android/iOS devices
- [ ] **U1:** Import one production-generated archive on Android and iOS
- [ ] **U2:** Verify Docker build and containerized dry run
- [ ] **V1:** Generate pipeline phase/artifact table from `StepSpec` registrations
- [ ] **V2:** Generate or snapshot CLI command/option documentation from argparse
- [ ] **V3:** Add test that documented archive paths match `PackageAcceptance` constants
- [ ] **V4:** Label every major feature as implemented, partial, or planned

**Deliverable:** Both apps read .story files and provide the full reading experience.

**Estimated time:** 8-10 weeks per platform (sequential, 16-20 weeks total if built by same developer; less if two developers work in parallel). Includes llama.cpp JNI/Swift binding integration, streaming GM chat, MIDI playback, state sync — conservative estimate for first-time mobile LLM integration.

**Status:** ✅ Source code scaffolding complete. Source compiles to valid Swift/Kotlin but has not been built with real NDK/Xcode — native llama.cpp compilation requires platform-specific toolchains (Android Studio + NDK, Xcode).

---

## Phase 7: Polish & Distribution

**Goal:** Production-ready software.

**Tasks:**
- [ ] PyInstaller packaging for App B (Windows .exe, macOS .app)
- [ ] Wine compatibility testing
- [ ] Performance optimization (profile, tune worker count)
- [x] CLI polish (progress bars, ETA, colored output — rich integration)
- [ ] Mobile polish (transitions, MIDI crossfade, GM chat history, dark mode, accessibility)
- [ ] Testing matrix (macOS, Windows, Wine/Linux, iOS 16+, Android 13+)
- [x] Model download helper (`pull_models.py` — Python cross-platform downloader)
- [ ] Distribution (GitHub releases, App Store, Google Play)

**Estimated time:** 3-4 weeks.

---

## Phase 7.5: Procedural World Generation

**Goal:** Generate physically coherent worlds procedurally, then let the LLM write meaning and prose on top — replacing "invent geography from scratch" with "interpret this real map."

### Architecture

Inspired by [df-style-worldgen](https://github.com/Dozed12/df-style-worldgen) (Dwarf Fortress-style 2D world generator, MIT license) but **not embedding that repository directly.** The original code is a 1,173-line monolithic prototype coupled to libtcod, archived in 2021. Instead, we extract and reimplement its algorithms in clean, tested modules.

```
Seed
  ↓
ProceduralWorldStep (new upstream phase)
  ├── elevation, temperature, precipitation, drainage
  ├── biomes, regions, prosperity
  ├── civilization placement + expansion simulation
  └── race/government assignment
  ↓
world_snapshot.json  (new intermediate contract — separate from narrative Bible)
  ↓
WorldBuilder (existing, updated to v2 prompt)
  ├── names and descriptions
  ├── cultures and factions
  ├── magic and mythology
  ├── historical interpretation
  └── narrative conflicts
  ↓
Story → CYOA Graph → Assets → .story
```

### Three Generation Modes

| Mode | Flag | Behavior |
|---|---|---|
| `narrative` | `--world-mode narrative` | Current LLM-first generation (default) |
| `procedural` | `--world-mode procedural` | Procedural map first, LLM enrichment after |
| `hybrid` | `--world-mode hybrid` | User constraints + procedural geography + LLM narrative |

### New Intermediate Contract: `world_snapshot.schema.json`

Separate from the narrative Bible. Summarizes the grid into regions, sites, borders, and resources — NOT raw tile data (which would consume too much LLM context).

```json
{
  "schema_version": 1,
  "seed": 42,
  "dimensions": {"width": 128, "height": 128},
  "regions": [
    {
      "id": "region_01",
      "biome": "temperate_forest",
      "elevation": "lowland",
      "climate": "wet_temperate",
      "prosperity": 0.72,
      "neighbors": ["region_02"],
      "sites": ["site_01"]
    }
  ],
  "sites": [
    {
      "id": "site_01",
      "region_id": "region_01",
      "type": "settlement",
      "civilization_id": "civ_01",
      "population": 3400
    }
  ],
  "civilizations": [
    {
      "id": "civ_01",
      "race": "human",
      "government": "elective_monarchy",
      "controlled_regions": ["region_01"]
    }
  ],
  "history": []
}
```

### Entity Mapping: Procedural → Narrative

| Procedural Data | StoryTeller Artifact |
|---|---|
| Region | Bible location |
| Settlement/site | Location or landmark |
| Civilization | Faction |
| Race | Culture/species |
| Government | Faction politics |
| Resource/prosperity | Economic conflict |
| Border | Travel or political constraint |
| Expansion history | Historical event |
| Route/neighbors | Valid story travel paths |
| Coordinates | Map and scene metadata |

The CYOA graph references location IDs from the snapshot — enabling validation of impossible travel (e.g., a choice jumping between disconnected regions).

### New Package: `forge/src/worldgen/`

```
forge/src/worldgen/
├── __init__.py
├── generator.py       # Top-level orchestrator
├── terrain.py         # Elevation, temperature maps (noise-based)
├── climate.py         # Precipitation, drainage, wind patterns
├── hydrology.py       # Rivers, lakes, watersheds
├── biomes.py          # Biome classification from terrain+climate
├── regions.py         # Region segmentation + neighbor detection
├── civilizations.py   # Starting sites, race/government assignment
├── simulation.py      # Time-stepped population expansion
├── adapter.py         # world_snapshot → Bible JSON mapping
└── models.py          # Dataclasses with deterministic RNG
```

### Updated Pipeline

```
forge generate --world-mode hybrid --world-size 128x128 --history-years 200 --seed 42

  ProceduralWorldStep  (new, no LLM)
       │
       ▼
  world_snapshot.json  (new schema)
       │
       ▼
  WorldBuilder v2      (updated prompt, accepts snapshot)
       │
       ▼
  bible.json → StoryWriter → GameDesigner → Assets → .story
```

### Tasks

- [ ] Design and validate `world_snapshot.schema.json`
- [ ] Implement `forge/src/worldgen/` package (10 modules)
  - Reimplement terrain/climate/hydrology algorithms (extracted from df-style-worldgen concepts)
  - Deterministic RNG seeded from pipeline seed
  - Civilization placement + population simulation
- [ ] Implement `ProceduralWorldStep` (PipelineStep, no LLM — pure Python)
- [ ] Implement `forge/src/worldgen/adapter.py` — snapshot → Bible prompt context
- [ ] Update `world_builder_v1.j2` → `world_builder_v2.j2`
  - Prompt changes from "invent a world" to "write lore for this generated world"
  - Inject region/civ/site summaries as structured constraints
- [ ] Add CLI: `--world-mode`, `--world-size`, `--history-years`
- [ ] Add graph validator rule: detect impossible travel (choices linking disconnected regions)
- [ ] Write tests: ProceduralWorldStep, adapter mapping, v2 prompt rendering, snapshot schema validation

**Prerequisite:** Stabilize Phase 0-5 production pipeline first. Adding procedural generation before the core pipeline is reliable would amplify existing orchestration, validation, resume, and reproducibility issues.

**Deliverable:** `forge generate --world-mode hybrid` produces a .story with real geography, simulated history, and LLM-written narrative — richer and more coherent than pure AI generation.

**Estimated time:** 2 weeks (reimplementation, not direct code reuse).

---

## Phase 8: Reproducibility & Migration Tools

**Goal:** Long-term maintainability.

**Tasks:**
- [ ] Seed verification tool: `forge verify --seed 42 --hash a1b2c3...`
- [ ] Schema migration tool: upgrade v1 .story to v2
- [ ] Model compatibility matrix: which models produce valid output
- [ ] Content hashing: SHA256 of content/ for integrity verification

**Estimated time:** 1-2 weeks.

---

## Timeline Summary

| Phase | Description | Estimate |
|---|---|---|
| 0 | Documentation | ✅ Complete |
| 0.5 | Pre-coding artifacts | ✅ Complete |
| 1 | Interfaces & model abstraction | ✅ Complete (166 tests) |
| 2 | Pipeline engine (Job Queue + Normalizer) | ✅ Complete |
| 3 | Schema & validation layer | ✅ Complete |
| 4 | World Builder + story generation | ✅ Complete |
| 5 | CYOA graph + assets + packaging | ✅ Complete (602 tests) |
| 5.6 | Forge hardening (suggestions.md + suggestions2.md) | 4-6 weeks |
| 6 | Mobile apps + cross-platform contracts + GM | 18-22 weeks |
| 7 | Polish & distribution | 3-4 weeks |
| 7.5 | Procedural worldgen (reimplementation) | 2 weeks |
| 8 | Reproducibility & migration | 1-2 weeks |
| **Total** | | **~38-52 weeks** |

**Milestone 0** ✅: Documentation complete. Schemas defined.
**Milestone 0.5** ✅: Prompts written, fixtures ready, project scaffolded.
**Milestone 1** ✅: Interfaces, pipeline engine, validators all complete. 0 mypy errors (src).
**Milestone 2** ✅: World Bible + story generation works (components).
**Milestone 3** ✅: CYOA graph + assets + packaging (components, 602 tests, 11/12 exit conditions met).
**Milestone 4** (Phase 5.6): Forge hardened — resume works, fingerprints enforced, pipeline plan declarative, package acceptance strict, atomic persistence, binary validation, artifact provenance, docs aligned.
**Milestone 5** (Phase 6): App A reads .story files. End-to-end experience.
**Milestone 6** (Phase 7): Production-ready, distributed.

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture being implemented
- **[design.md](design.md)** — Behavioral design with pipeline flows
- **[test.md](test.md)** — Test strategy for each phase
