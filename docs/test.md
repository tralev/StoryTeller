# StoryTeller — Test Strategy

## Testing Philosophy

StoryTeller has unique testing challenges:
- LLM output is non-deterministic — we test **structure** and **constraints**, not exact text
- Generation is slow — unit tests use mocks; integration tests are gated
- Pipeline state is complex — checkpoint/resume needs exhaustive testing
- Reproducibility is scoped to same-machine — identical inputs + same hardware = identical outputs
- Mobile has two platforms — shared test scenarios, platform-specific execution

---

## Test Categories

### 1. Unit Tests (fast, no LLM, no models)

Run on every commit. Target: < 5 seconds for full suite.

#### Interfaces & Model Abstraction

| Test | What It Verifies |
|---|---|
| `test_interfaces.py` | All Protocol classes defined correctly, can be implemented by mocks |
| `test_config.py` | Config YAML loads correctly, interface→concrete mapping resolves, model swap |
| `test_backend_protocols.py` | All 5 backends satisfy their Protocol interfaces at runtime |

#### Backend Layer

| Test | What It Verifies |
|---|---|
| `test_midi_backend.py` | ABC→MIDI conversion (real music21), validation, deterministic output, stub generate |
| `test_gm_backend.py` | LlamaCppGameMaster stub attributes, load/unload, answer() raises NotImplementedError |
| `test_model_manager.py` | Register/load/unload, RAM budget enforcement, unload_to_fit, FIFO ordering |

#### Pipeline Engine

| Test | What It Verifies |
|---|---|
| `test_job_queue.py` | execute_step/execute_parallel, result tracking, event logging, failure propagation | 12 |
| `test_job_queue_extended.py` | PipelineContext, FailurePolicy, parallel timing, multi-phase pipeline simulation | 10 |
| `test_normalizer.py` | Enum normalization, array sorting, flag names, JSON formatting, whitespace |
| `test_normalizer_extended.py` | Entity ID warnings, asset path normalization |
| `test_checkpoint.py` | SQLite save/load/resume, phase tracking, delete/clear, output parsing |

#### Validation Layer

| Test | What It Verifies |
|---|---|
| `test_schema_validator.py` | Valid JSON passes, missing fields fail, manifest validation, error path formatting |
| `test_cross_ref_checker.py` | Entity IDs (graph+story), node targets, flag consistency, bible node refs, prefix matching |
| `test_graph_validator.py` | Valid graph, unreachable/orphan/dead-end/cycle detection, edge cases, format_for_retry |
| `test_integration_validators.py` | End-to-end chain: schema → cross_ref → graph for all 3 artifacts |

#### Reproducibility & Determinism (tested via Normalizer)

| Test | What It Verifies |
|---|---|
| `test_normalizer.py::TestJsonNormalization` | `json.dumps(sort_keys=True)` produces identical output; floats rounded to 6 places; roundtrip stable |
| `test_normalizer.py::TestProcess` | `process()` is idempotent — running twice produces same output |

> Full reproducibility tests (SHA256 match, ZIP determinism, seed propagation) are implemented and passing.

#### Phase 4: World Builder + Story Generation

| Test | What It Verifies | Tests |
|---|---|---|
| `test_world_builder.py` | Prompt rendering, metadata injection, determinism, normalization | 6 |
| `test_art_director.py` | Style bible generation, entity injection, edge cases | 9 |
| `test_story_writer.py` | Outline + chapters, continuity, entity usage, malformed output | 13 |
| `test_consistency.py` | Entity presence, dead characters, mortality rules, bible resilience | 15 |
| `test_bible_helpers.py` | Shared summarize_bible helper: all 4 caller configs, edge cases | 18 |
| `test_cli.py` | CLI parser: all 11 commands, argument parsing, required checks | 20 |

#### Phase 5: CYOA Graph + Asset Generation

**Operational proof (2026-08-04):** Real-model smoke test — Qwen 7B Q4_K_M loads/generates/unloads (16s), WorldBuilder produces "Smoke Test World" with 4 characters, 3 locations (3m10s). 4/4 GGUF models confirmed in ai_models/. 3/4 smoke tests pass; Bible+Story pipeline exceeds 10 min on CPU (expected). + Packaging

| Test | What It Verifies | Tests |
|---|---|---|
| `test_game_designer.py` | 3-mode CYOA graph (decision points, skeleton, node text), merge validation, KeyError resilience | 36 |
| `test_image_generator_step.py` | Style bible injection, 512x512+thumbnails, QUARANTINE, batch | 26 |
| `test_music_generator_step.py` | ABC→MIDI, tone mapping, validation, QUARANTINE, batch | 31 |
| `test_indexer.py` | GM keyword index, entity cache, reveal_after_node gating, node contexts, _find_related, _extract_mentioned_entities | 33 |
| `test_packager.py` | Deterministic ZIP structure, SHA256 hashing, manifest validation | 24 |
| `test_orchestrator.py` | Pipeline scheduler, checkpoints, ABORT/QUARANTINE, progress | 16 |
| `test_integration_pipeline.py` | End-to-end Bible→.story, context flow, determinism, error recovery | 9 |

#### Phase 5.5: Integration Hardening

| Test | What It Verifies | Tests |
|---|---|---|
| `test_production_wiring.py` | GenerateStory.execute() with tracked fakes: full pipeline, canonical keys, resume shape, validator wiring, determinism, manifest fields, error propagation, batch quarantine | 9 |
| `test_artifact_store.py` | Streaming write-through artifact storage | 24 |
| `test_bible_helpers.py` | Shared summarize_bible helper (counted in Phase 4) | 18 |

**Total: 569 tests (all phases). mypy: 0 errors (src + scripts + tests).**

---

### 2. Integration Tests (requires models, gated)

Run before merging to main or on CI with GPU. These use real GGUF models.

#### World Builder Integration

```
Test: Generate World Bible end-to-end
Input: --seed 42 --tone dark_fantasy --title "Test World"
Model: TextGenerator (Qwen 7B)
Validates:
  - Output is valid JSON
  - Passes bible.schema.json validation
  - All required top-level keys present
  - At least 3 characters, 2 locations, 1 faction, 1 magic school
  - All entity IDs unique and normalized (char_01 format)
  - All cross-references point to existing IDs
  - Version metadata present and correct
  - RAM < 5 GB, time < 10 min
```

#### Determinism Integration

```
Test: Same seed → same output
Setup: Run pipeline twice with --seed 42
Validates:
  - bible.json SHA256 identical
  - story.json SHA256 identical
  - graph.json SHA256 identical
  - .story file SHA256 identical
```

#### Parallelism Integration

```
Test: Parallel image generation is faster than sequential
Setup: Run image generation with 1 worker, then 4 workers
Validates:
  - 4 workers completes faster than 1 worker (SDXL parallelism across nodes)
  - Output is identical regardless of worker count
```

#### Job Queue Integration

```
Test: Jobs execute in correct order
Validates:
  - Sequential jobs (Bible→Story→Graph) never run in parallel
  - Parallel jobs (images, MIDI) run concurrently
  - Sequential jobs (text generation) never run in parallel
  - Queue drains completely
  - Failed jobs trigger retry
```

#### Full Pipeline Integration

```
Test: Bible → .story end-to-end
Models: All three (TextGenerator, Validator, ImageGenerator)
Validates:
  - Pipeline completes without unhandled errors
  - .story ZIP is valid and reproducible
  - content/ and save/ directories present
  - manifest.json matches generated content
  - gm_index.json covers all entity names
  - Total time < 24 hours, peak RAM < 10 GB
```

#### Checkpoint/Resume Integration

```
Test: Resume from each pipeline step
Setup: Run pipeline, kill at step N
Validates:
  - forge resume continues from step N
  - No duplicate work
  - Final output identical to uninterrupted run
  - Repeat for N = 2, 4, 6, 8
```

---

### 3. Mobile Tests

#### Android

| Test | Type | What It Verifies |
|---|---|---|
| `.story` import | Integration | ZIP extracted, content/ + save/ parsed |
| content/ immutability | Integration | content/ files are never modified after import |
| save/ persistence | Integration | save_state.json written on choice, preserved across app restarts |
| Page rendering | UI | Text, choices, images display correctly |
| MIDI playback | Integration | Looping, scene crossfade, volume control |
| GM retrieval | Unit | Keyword extraction, index lookup, context assembly |
| GM streaming | Integration | Tokens appear incrementally, UI stays responsive |
| Flag system | Unit | Flags set on choice, conditional text applied, endings gated |
| Cloud sync | Integration | save/ syncs independently of content/ |
| Memory | Integration | GM LLM stays under 3 GB, no OOM |

#### iOS

Same test scenarios as Android, using Swift-native testing.

---

### 4. Performance Tests

| Test | Metric | Threshold |
|---|---|---|
| Bible generation | Wall time | < 5 min |
| Chapter generation (per chapter) | Wall time | < 15 min |
| Node text generation (sequential) | Wall time | < 45 min (all 15 nodes) |
| Image generation (parallel) | Wall time | < 40 min (all 15 images) |
| MIDI generation (parallel) | Wall time | < 5 min (all 15 tracks) |
| Full pipeline (typical) | Wall time | < 4 hours (8+ core CPU) |
| Full pipeline (worst case) | Wall time | < 24 hours (4-core, throttled) |
| App B peak RAM | RSS | < 10 GB |
| App A idle RAM | RSS | < 500 MB |
| App A GM active RAM | RSS | < 3 GB |
| GM response time | Time to first token | < 2 seconds |
| .story import time | Wall time | < 5 seconds |
| Same-machine reproducibility | SHA256 match | 100% (same machine, same config) |

---

### 5. Quality Tests (Manual)

Run per-release, require human judgment:

- **Bible quality:** Characters distinctive? Magic system interesting? World coherent?
- **Story quality:** Prose engaging? Plot logical? Characters consistent?
- **Graph quality:** Choices meaningful? Branches distinct? Endings satisfying?
- **Image quality:** Illustrations appealing? Style consistent? Match scenes?
- **Music quality:** Mood fit? Looping smooth? Atmosphere enhanced?
- **GM quality:** Answers accurate? In character? Avoids spoilers?

---

## Test Execution

### CI Pipeline (GitHub Actions) — Proposed

> ⚠️ **Not yet implemented.** No `.github/workflows` exist. All testing is manual/local. The plan below describes the intended CI setup.

```yaml
# Every push:
- Unit tests (fast, no models)
- Linting (ruff)
- Type checking (mypy)

# PR to main:
- Unit tests + linting + type checking
- Determinism tests (mock pipeline)
- Schema validation against all fixtures
- Normalizer tests

# Weekly:
- Full integration suite (requires GPU runner)
- Performance benchmarks
- Determinism verification (real models)

# Per-release:
- Full integration suite
- Manual quality review
- Mobile testing on physical devices
```

### Running Tests Locally

```bash
# Unit tests (fast, no models)
pytest tests/ -m "not integration" -v

# Determinism tests
pytest tests/ -m determinism -v

# Integration tests (requires models)
pytest tests/ -m integration -v --timeout 3600

# With coverage
pytest tests/ -m "not integration" --cov=src --cov-report=html
```

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture to validate against
- **[api.md](api.md)** — Interface definitions under test
- **[schemas/](schemas/)** — JSON Schema contracts used by validators
- **[roadmap.md](roadmap.md)** — Development phases with test milestones
