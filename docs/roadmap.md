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
- [ ] Write all 6 prompt templates in `forge/src/prompts/`
  - `world_builder.j2` — generates structured World Bible from tone + title
  - `story_writer.j2` — generates chapter text with Bible injection
  - `game_designer.j2` — extracts decision points, builds graph skeleton, writes node text
  - `art_director.j2` — generates image prompts with style bible suffix
  - `composer.j2` — detects music tone, generates ABC notation
  - `game_master.j2` — answers reader questions with injected context
- [ ] Create `config/models.yaml` — interface→concrete model mapping
- [ ] Create `forge/pyproject.toml` — dependencies, dev tools, project metadata
- [ ] Create `.gitignore` — exclude models, venv, output, secrets
- [ ] Create test fixtures in `forge/tests/fixtures/`
  - `bible_valid.json` / `bible_invalid.json`
  - `story_valid.json`
  - `graph_valid.json` / `graph_with_orphan.json` / `graph_with_cycle.json`
  - `gm_index_valid.json`
  - `abc_valid.txt` / `abc_invalid.txt`
  - `style_bible_valid.json`
- [ ] Validate all JSON schemas against fixtures — catch schema errors now
- [ ] Scaffold `forge/src/` directory tree per `arch.md`
- [ ] Initialize git repository
- [ ] Create empty `droid/`, `ios/`, `mac/`, `windows/` directories

**Deliverable:** Ready to write Python code. Project structure exists, prompts are versioned, schemas validate, fixtures enable TDD.

**Estimated time:** 2-3 days.

> ⚠️ **Development principle: build vertically first.** Before adding parallelism, retries, or optimization, prove the core pipeline end-to-end: generate one valid World Bible → one story → one graph → package one .story → load it on mobile. Only then expand horizontally. This gives early feedback and reduces over-engineering risk. Phases 1-5 should produce a working (slow, single-threaded) pipeline before Phase 2's Job Queue adds parallelism.

---

## Phase 1: Interfaces & Model Abstraction Layer

**Goal:** Define all interfaces (TextGenerator, Validator, ImageGenerator, MusicGenerator, GameMaster) and their concrete implementations.

**Tasks:**
- [ ] Define `forge/src/interfaces/` — all Protocol classes
- [ ] Implement `forge/src/backends/llm_backend.py` — concrete TextGenerator + Validator
  - ModelManager with load/unload lifecycle
  - GGUF model path resolution from config
  - RAM tracking and budget enforcement
  - Async generation with configurable temperature and seed
- [ ] Implement `forge/src/backends/image_backend.py` — concrete ImageGenerator
  - SDXL-Turbo loading and generation
  - 512×512 PNG output
  - Thumbnail generation (128×128)
  - Seed propagation for determinism
- [ ] Implement `forge/src/backends/midi_backend.py` — concrete MusicGenerator
  - ABC notation → MIDI via music21
  - MIDI validation (playable, correct duration)
- [ ] Implement `forge/src/config.py`
  - Load models.yaml
  - Resolve interfaces to concrete implementations
  - Environment variable overrides
- [ ] Write unit tests for all interfaces and backends

**Deliverable:** Can load any configured model, generate text/images/MIDI through interfaces. Swapping models requires only config change.

**Estimated time:** 1-2 weeks.

---

## Phase 2: Pipeline Engine (Job Queue + Worker Pool)

**Goal:** The Generator → Validator → Normalizer → Commit pipeline with parallel execution.

**Tasks:**
- [ ] Implement `forge/src/job_queue.py`
  - Async job queue with configurable worker count
  - Worker pool that executes Job → Generator → Validator → Normalizer → Commit
  - Retry logic (max 3 attempts with error feedback)
  - Thread-safe commit (multiple workers writing results)
  - Job dependency tracking (sequential phases wait for previous)
- [ ] Implement `forge/src/normalizer.py`
  - Entity ID normalization
  - Naming convention enforcement
  - Array sorting
  - Whitespace cleanup
  - JSON formatting (sorted keys, 2-space indent)
  - Asset path normalization
  - Flag name normalization
- [ ] Implement `forge/src/models/base.py`
  - Abstract PipelineStep using interfaces
  - Retry loop with error feedback
  - Checkpoint integration
- [ ] Write unit tests for job queue, worker pool, normalizer

**Deliverable:** Job Queue executes jobs in parallel. Normalizer enforces all conventions. Can run a dummy pipeline (no LLM).

**Estimated time:** 1-2 weeks.

---

## Phase 3: Schema & Validation Layer

**Goal:** All JSON schemas defined and validators working.

**Tasks:**
- [ ] Write all JSON Schema files in `docs/schemas/`
- [ ] Implement `forge/src/validators/schema_validator.py`
  - Load schemas, validate JSON, format errors for LLM retry feedback
- [ ] Implement `forge/src/validators/cross_ref_checker.py`
  - Entity ID resolution, node target validation, flag consistency
- [ ] Implement `forge/src/validators/graph_validator.py`
  - Reachability, orphan detection, dead-end detection, cycle detection
- [ ] Write unit tests for all validators with fixtures

**Deliverable:** Can validate any JSON against schemas and detect structural/graph issues.

**Estimated time:** 1 week.

---

## Phase 4: World Builder + Story Generation

**Goal:** Bible and linear story generation working.

**Tasks:**
- [ ] Write prompt templates: `world_builder.j2`, `style_bible.j2`, `story_writer.j2`, `consistency_check.j2`
- [ ] Implement `forge/src/models/world_builder.py`
- [ ] Implement `forge/src/models/art_director.py` (style bible)
- [ ] Implement `forge/src/models/story_writer.py` (outline + chapters)
- [ ] Implement `forge/src/validators/consistency.py` (Bible-violation detection)
- [ ] Implement `forge/src/storage/checkpoint.py` (SQLite state)
- [ ] Integration test: Bible + story generation end-to-end

**Deliverable:** `forge generate-bible` and `forge generate-story` produce valid, consistent output.

**Estimated time:** 2-3 weeks.

---

## Phase 5: CYOA Graph + Asset Generation

**Goal:** Complete App B pipeline — from Bible to .story package.

**Tasks:**
- [ ] Write prompt templates: `game_designer.j2`, `art_director.j2`, `composer.j2`, `game_master.j2`
- [ ] Implement `forge/src/models/game_designer.py`
  - Decision points extraction
  - Graph skeleton generation
  - Sequential node text generation (one shared LLM instance)
  - Consequence flag assignment
  - Conditional text generation
- [ ] Implement parallel image generation pipeline
- [ ] Implement parallel music generation pipeline
- [ ] Implement `forge/src/storage/indexer.py` (GM index)
- [ ] Implement `forge/src/storage/packager.py` (deterministic .story ZIP)
  - Sorted JSON keys, fixed float precision, normalized timestamps
  - content/ and save/ directory structure
- [ ] Implement `forge/src/orchestrator.py`
  - Pipeline scheduler (sequential + parallel phases)
  - Checkpoint integration
  - Progress reporting
- [ ] CLI entry point
- [ ] Full integration test: Bible → .story end-to-end
- [ ] Determinism test: same seed → identical .story (SHA256 match)

**Deliverable:** Running `forge generate --seed 42` produces a complete, same-machine-reproducible .story file.

**Estimated time:** 3-4 weeks.

---

## Phase 6: Mobile Player (App A)

**Goal:** iOS and Android apps that read .story files.

### Android (Kotlin + Jetpack Compose)

- [ ] Project setup with Gradle, Compose, llama.cpp JNI
- [ ] .story import: file picker, ZIP extraction, content/save split
- [ ] Book reader: page rendering, choice buttons, image display
- [ ] MIDI player: SoundFont bundling, looping, crossfade
- [ ] Game Master: llama.cpp integration, gm_index retrieval, streaming
- [ ] State management: flags, conditional text, ending detection
- [ ] Save state persistence + cloud sync of save/
- [ ] Library screen with progress indicators

### iOS (Swift + SwiftUI)

- [ ] Project setup with Xcode, SwiftUI, llama.cpp Swift bindings
- [ ] .story import: document picker, content/save split
- [ ] Book reader: SwiftUI views, AsyncImage
- [ ] MIDI player: AVAudioEngine, bundled SoundFont
- [ ] Game Master: llama.cpp, gm_index retrieval, streaming
- [ ] State management + save persistence + cloud sync

**Deliverable:** Both apps read .story files and provide the full reading experience.

**Estimated time:** 8-10 weeks per platform (includes llama.cpp JNI/Swift binding integration, streaming GM chat, MIDI playback, state sync — conservative estimate for first-time mobile LLM integration).

---

## Phase 7: Polish & Distribution

**Goal:** Production-ready software.

**Tasks:**
- [ ] PyInstaller packaging for App B (Windows .exe, macOS .app)
- [ ] Wine compatibility testing
- [ ] Performance optimization (profile, tune worker count)
- [ ] CLI polish (progress bars, ETA, colored output)
- [ ] Mobile polish (transitions, MIDI crossfade, GM chat history, dark mode, accessibility)
- [ ] Testing matrix (macOS, Windows, Wine/Linux, iOS 16+, Android 13+)
- [ ] Model download helper (first-run experience)
- [ ] Distribution (GitHub releases, App Store, Google Play)

**Estimated time:** 3-4 weeks.

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
| 0.5 | Pre-coding artifacts | 2-3 days |
| 1 | Interfaces & model abstraction | 1-2 weeks |
| 2 | Pipeline engine (Job Queue + Normalizer) | 1-2 weeks |
| 3 | Schema & validation layer | 1 week |
| 4 | World Builder + story generation | 2-3 weeks |
| 5 | CYOA graph + assets + packaging | 3-4 weeks |
| 6 | Mobile apps (iOS + Android) | 16-20 weeks |
| 7 | Polish & distribution | 3-4 weeks |
| 8 | Reproducibility & migration | 1-2 weeks |
| **Total** | | **~30-39 weeks** |

**Milestone 0** (now): Documentation complete. Schemas defined.
**Milestone 0.5** (Phase 0.5): Prompts written, fixtures ready, project scaffolded.
**Milestone 1** (Phase 4): World Bible + story generation works.
**Milestone 2** (Phase 5): Full App B pipeline. Same-machine-reproducible .story output.
**Milestone 3** (Phase 6): App A reads .story files. End-to-end experience.
**Milestone 4** (Phase 7): Production-ready, distributed.

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture being implemented
- **[design.md](design.md)** — Behavioral design with pipeline flows
- **[test.md](test.md)** — Test strategy for each phase
