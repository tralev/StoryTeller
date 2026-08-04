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

**Status:** ✅ Complete. 534 tests (all phases), mypy: 0 errors.

**Estimated time:** 3-4 weeks (completed).

---

## Phase 5.5: Integration Hardening

**Goal:** Bridge the gap between component-complete (all units work in isolation) and product-complete (the end-to-end `forge generate` works with real models, validators connected, manifest generated, resume reliable, reproducibility verified).

**Why this phase exists:** The audits in `tmp/` (docs-codebase-audit, missing, micro-macro-design-review, suggestions, mypy-full-review) all converge on the same finding: Phases 0-5 built all the right components but did not fully connect them into the production workflow that the roadmap promises. This phase closes that gap without adding new generation features.

### A: Application Service Layer

- [x] Create `forge/src/application/` package:
  - `generate_story.py` — `GenerateStory` service (shared by CLI + overnight mode)
  - `resume_story.py` — `ResumeStory` service
  - `package_story.py` — `PackageStory` service
  - `validate_project.py` — `ValidateProject` service
- [x] Refactor `cli.py` to invoke `GenerateStory` instead of assembling pipeline directly
- [x] Refactor `run_overnight.py` to invoke the same `GenerateStory` service (monitoring becomes an observer, not a separate pipeline)
- [x] Add `GenerationRequest` dataclass: seed, title, tone, temperature, output_dir, config_path
- [x] Add `GenerationResult` dataclass: package_path, package_hash, artifacts, events, duration

### B: Model Lifecycle Integration

- [x] Connect `ModelManager` to `GenerateStory` — models load before generation, unload after (even on failure/cancellation)
- [x] `_cmd_generate` must call `backend.load()` before the orchestrator invokes generation (now via `resource_scope`)
- [x] Resource scoping: `async with model_resources.acquire(ModelRole.TEXT): ...` via manager.resource_scope()
- [x] Document actual model lifecycle: text model → Bible/Style/Story/Graph/Music prompts → unload → image model → Images → unload → Index/Package
- [ ] Fix `config/models.yaml` → image fields like `size`/`steps` should be validated, not silently discarded by `ModelConfig.from_dict()`

### C: Validation Wiring

- [x] Make deterministic validators mandatory in production step registrations (not silently skipped when `validator=None`)
- [x] Create explicit `ValidationPlan` per artifact:
  | Artifact | Required Checks |
  |---|---|
  | Bible | JSON Schema + internal cross-references |
  | Style Bible | JSON Schema |
  | Story | JSON Schema + Bible consistency (programmatic + LLM critique) |
  | Graph | JSON Schema + cross-references + topology (reachability, orphan, cycle) |
  | GM Index | JSON Schema + referenced entity/node existence |
  | Manifest | JSON Schema + file inventory/hash verification |
  | Package | Archive layout + all contained contracts |
- [x] Connect `CrossRefChecker`, `GraphValidator`, `ConsistencyChecker` to production `GameDesigner` and `StoryWriter` steps
- [x] Implement `LlamaCppValidator` (currently raises `NotImplementedError`) — prompt construction → parse `ValidationResult` → retry feedback
- [x] Feed structured `ValidationIssue` objects (code, path, message, retryable flag) into retry prompts

### D: Manifest & Package Acceptance

- [x] Implement `ManifestBuilder` step — generates `manifest.json` that satisfies `manifest.schema.json`:
  - Story/package ID, title, seed
  - Generator and pipeline versions
  - Model identities and file hashes
  - Prompt versions/hashes
  - Entry point, file inventory, artifact dependencies
  - Canonical content hash (from canonical metadata only, NOT wall-clock data)
- [x] ManifestBuilder must run BEFORE Packager — packager no longer patches an empty dictionary
- [x] Implement `PackageAcceptance` gate — reopen the .story ZIP and validate as an external client:
  - Reject unsafe/absolute ZIP paths
  - Verify all required entries exist
  - Parse and validate every JSON artifact against its schema
  - Verify manifest inventory and content hashes match files
  - Ensure graph entry point exists and all referenced images/MIDI files are present
  - Ensure no undeclared content files (unless explicitly allowed)
- [ ] `forge verify` command must pass PackageAcceptance

### E: Resume & Reproducibility

- [x] Fix output key ownership: `JobQueue` and `Orchestrator` both write to `context.outputs` with different keys — choose ONE owner (orchestrator) and ONE canonical key (`output_key`, not internal step name)
- [x] Fix resume symmetry: normal execution stores `bible`, resume currently restores `world_builder` → downstream steps fail. Checkpoint must retain both step_id + output_key; restore using output_key
- [x] Add run fingerprint to checkpoints:
  - Seed and generation parameters
  - Config hash
  - Model file hashes
  - Prompt file hashes
  - Schema versions
  - Pipeline/code version
- [x] Resume must reject if fingerprint doesn't match (seed changed, model updated, schema upgraded)
- [ ] Separate canonical metadata from operational metadata:
  - **Canonical** (included in content hash): seed, model hashes, prompt hashes, schema versions, normalized params
  - **Operational** (excluded from content hash): started_at, completed_at, duration, host, log paths, RAM samples
- [ ] Remove `created_at` (wall-clock time) from artifact IDs and content hashes
- [ ] Define the reproducibility guarantee in testable terms: "Given identical canonical inputs, model files, prompt files, backend versions, thread configuration, and hardware profile, StoryTeller produces identical canonical content and archive bytes."
- [ ] Add two determinism test levels:
  - Fake-backed determinism on every push
  - Real-model determinism on a controlled machine (manual or scheduled)
- [ ] Add atomic artifact commits: serialize to temp file → validate → atomic rename → commit checkpoint → append event
- [ ] On resume, reconcile checkpoint hashes with disk artifacts before trusting either source

### F: Failure Handling & Observability

- [ ] Introduce structured error taxonomy:
  ```
  StoryTellerError
  ├── ConfigurationError      (terminal)
  ├── MissingDependencyError  (terminal)
  ├── ModelLoadError          (terminal or operator-retry)
  ├── GenerationError         (possibly retryable)
  ├── ValidationError         (retryable when caused by generated content)
  ├── PersistenceError        (terminal)
  └── PackageValidationError  (terminal)
  ```
- [ ] Only retry explicitly retryable errors — never quarantine config, resource, or persistence defects as if they were bad model output
- [ ] Apply `FailurePolicy.QUARANTINE` only to independently recoverable item jobs (one node image, one MIDI track) — not phase-wide dependencies
- [ ] Return structured `BatchResult`: `completed: dict[str, T]`, `quarantined: dict[str, FailureRecord]`
- [ ] Standardize event types: `pipeline_started`, `model_loaded`, `step_started`, `validation_failed`, `step_retrying`, `artifact_committed`, `item_quarantined`, `checkpoint_saved`, `pipeline_completed`, `pipeline_failed`
- [ ] Handle `KeyboardInterrupt`/cancellation gracefully: finish atomic writes, save last checkpoint, unload models, emit cancellation event, exit distinct status code

### G: Type System & Mypy Cleanup

- [ ] Fix `TextGenerator.generate_stream` protocol: change from `async def` with no yield to `def ... -> AsyncIterator[str]` (mypy interprets these as different contracts)
- [ ] Create shared fully-typed fake generators in `tests/fakes.py` (implement all protocol members: provider, model_name, quantization, generate_stream, load, unload, ram_usage_mb)
- [ ] Fix 3 incorrect return annotations in `scripts/dry_run.py` and `tests/`
- [ ] Add explicit types to test dictionaries, fixtures, and callback functions (eliminate `no-untyped-def` and `no-untyped-call` errors)
- [ ] Add `type: ignore` or proper annotations for optional-value accesses in `tests/test_cli.py` and `tests/test_integration_pipeline.py`
- [ ] Goal: `mypy src scripts tests` → 0 errors (currently 150 errors in 18 files, src is clean)

### H: Batch Processing Refactor

- [ ] Split image/music batch steps into individually schedulable node jobs
- [ ] Add `asyncio.Semaphore(config.pipeline.workers)` to enforce actual worker limits
- [ ] Per-node checkpointing and progress events
- [ ] Apply the same model to node text generation in `GameDesigner`
- [ ] Keep text-model work serial unless the backend explicitly declares concurrency support

### I: Production-Wiring Tests

- [ ] Add fake-backed production-wiring integration test: invokes `GenerateStory` service, verifies:
  - All expected artifact keys exist
  - Every artifact written once under canonical filename
  - Resume restores same context shape
  - Required validators run
  - Model load/unload order is correct
  - Valid manifest created
  - Final ZIP passes `PackageAcceptance`
- [ ] Add real-model end-to-end acceptance test (controlled small story, ~3 nodes, ~30 min)
- [ ] Verify generated .story imports on both Android and iOS parsers
- [ ] Add command-level integration tests: `forge generate`, `forge resume`, `forge package`, `forge validate-all`, `forge verify`

### J: Documentation Alignment

- [ ] Fix archive layout diagrams — all should use root-level `manifest.json` (not `content/manifest.json`)
- [ ] Fix malformed heading in `arch.md`: `# StoryTeller — Technical Architecture## Core Architectural Pattern...`
- [ ] Replace placeholder clone URL in `readme.md` (`yourorg/storyteller` → `tralev/StoryTeller`)
- [ ] Change roadmap status from blanket "Complete" to distinguish: component-tested vs production-integrated
- [ ] Remove repository-wide "0 mypy errors" claim until true (currently `src/` is clean but `scripts/` + `tests/` has 150)
- [ ] Mark CI section in `test.md` as "proposed" (no `.github/workflows` exist)
- [ ] Label planned vs implemented behavior consistently across all docs
- [ ] Add "Current Limitations" section to `readme.md`
- [ ] Correct mobile phase status to distinguish implemented, unverified, and remaining capabilities

### K: Shared Contract Fixtures

- [ ] Create canonical `.story` v1 fixtures:
  - Minimal valid `.story` (1 node)
  - Complete representative `.story` (15 nodes, images, MIDI)
  - Invalid archives: missing manifest, bad graph refs, path traversal, unsupported version, incorrect hash
- [ ] Run same fixtures through Python, Android, and iOS tests
- [ ] Add package compatibility version to manifest — mobile import handles: supported version, older migratable version, newer unsupported version
- [ ] Define one versioned `.story` specification shared by schemas, packager, CLI validators, Android parser, iOS parser, docs, and test fixtures

---

### Phase 5.5 Exit Conditions

The phase is complete ONLY when ALL of the following are true:

- [ ] `forge generate` and `run_overnight.py` share one `GenerateStory` service
- [ ] Required models load and unload automatically (no manual setup)
- [ ] Normal execution and resume expose identical canonical artifact keys
- [ ] Every required artifact passes deterministic validation before commit
- [ ] A schema-valid manifest is always produced
- [ ] The completed archive passes external `PackageAcceptance`
- [ ] A fake-backed end-to-end test uses the production assembly path
- [ ] At least one real-model end-to-end run succeeds (small, controlled)
- [ ] Resume after each major phase is verified (produces same canonical archive)
- [ ] `mypy src scripts tests` → 0 errors
- [ ] Documentation accurately distinguishes implemented from planned behavior
- [ ] One canonical `.story` fixture is accepted by Forge, Android, and iOS

**Estimated time:** 2-3 weeks.

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
| 5 | CYOA graph + assets + packaging | ✅ Complete (534 tests) |
| 5.5 | Integration hardening | 2-3 weeks |
| 6 | Mobile apps (iOS + Android) | 16-20 weeks |
| 7 | Polish & distribution | 3-4 weeks |
| 7.5 | Procedural worldgen (reimplementation) | 2 weeks |
| 8 | Reproducibility & migration | 1-2 weeks |
| **Total** | | **~33-44 weeks** |

**Milestone 0** ✅: Documentation complete. Schemas defined.
**Milestone 0.5** ✅: Prompts written, fixtures ready, project scaffolded.
**Milestone 1** ✅: Interfaces, pipeline engine, validators all complete. 0 mypy errors (src).
**Milestone 2** ✅: World Bible + story generation works (components).
**Milestone 3** ✅: CYOA graph + assets + packaging (components, 534 tests).
**Milestone 4** (Phase 5.5): Production pipeline verified end-to-end — `forge generate` produces valid, accepted .story with real models.
**Milestone 5** (Phase 6): App A reads .story files. End-to-end experience.
**Milestone 6** (Phase 7): Production-ready, distributed.

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture being implemented
- **[design.md](design.md)** — Behavioral design with pipeline flows
- **[test.md](test.md)** — Test strategy for each phase
