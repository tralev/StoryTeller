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
| `test_model_config.py` | Config YAML loads correctly, interface→concrete mapping resolves |
| `test_model_swap.py` | Changing config swaps concrete implementation without code changes |

#### Backend Layer

| Test | What It Verifies |
|---|---|
| `test_llm_backend_mock.py` | Prompt formatting, response parsing, retry logic, token counting, streaming, seed propagation |
| `test_image_backend_mock.py` | Resolution validation, file format, seed propagation, error handling |
| `test_midi_backend.py` | ABC→MIDI with known-good ABC, validation of output MIDI, error on malformed ABC |

#### Pipeline Engine

| Test | What It Verifies |
|---|---|
| `test_job_queue.py` | Enqueue/dequeue, worker pool execution, parallel job completion, drain behavior |
| `test_worker.py` | Generator→Validator→Normalizer→Commit flow, retry on validation failure, max retries exceeded |
| `test_normalizer.py` | ID normalization, naming conventions, array sorting, whitespace, JSON formatting, path normalization, flag name normalization |
| `test_checkpoint.py` | Save/load state, resume from step N, step status transitions, corrupted DB recovery |

#### Validation Layer

| Test | What It Verifies |
|---|---|
| `test_schema_validator.py` | Valid JSON passes, missing fields fail, wrong types fail, errors formatted for LLM feedback |
| `test_cross_ref_checker.py` | Valid cross-refs pass, broken char_id fails, orphaned targets detected, missing flags caught |
| `test_graph_validator.py` | Valid graph passes, orphan node detected, unreachable node detected, cycle detected, dead-end without ending flag detected |

#### Reproducibility & Determinism

| Test | What It Verifies |
|---|---|
| `test_deterministic_json.py` | `json.dumps(sort_keys=True)` produces identical output for same dict |
| `test_deterministic_zip.py` | Same files produce bit-identical ZIP archive (sorted entries, normalized timestamps) — ZIP-level determinism is universal |
| `test_same_machine_reproducibility.py` | Mock pipeline with same seed + same config produces identical output twice on same machine |
| `test_float_precision.py` | All floats rounded to 6 decimal places before serialization |


#### Immutability

| Test | What It Verifies |
|---|---|
| `test_content_readonly.py` | content/ files are never modified after initial write |
| `test_save_isolation.py` | save/ data is written separately from content/ |
| `test_packager_structure.py` | .story ZIP contains content/ and save/ directories |

#### Storage Layer

| Test | What It Verifies |
|---|---|
| `test_packager.py` | All files present → valid .story; missing file → error; ZIP structure correct |
| `test_indexer.py` | Keyword extraction, alias generation, morphological variants, n-gram indexing, entity cache, node context mapping |

#### Versioning

| Test | What It Verifies |
|---|---|
| `test_version_metadata.py` | Every output artifact includes schema_version, generator_version, pipeline_version, created_at, model_versions, seed |
| `test_version_migration.py` | v1 schema can be detected, migration path exists |

#### Reproducibility

| Test | What It Verifies |
|---|---|
| `test_seed_propagation.py` | Seed is recorded in every artifact's metadata |
| `test_seed_regeneration.py` | Same seed + same mock models = identical output |

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

### CI Pipeline (GitHub Actions)

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
cd forge && pytest tests/ -m "not integration" -v

# Determinism tests
cd forge && pytest tests/ -m determinism -v

# Integration tests (requires models)
cd forge && pytest tests/ -m integration -v --timeout 3600

# With coverage
cd forge && pytest tests/ -m "not integration" --cov=src --cov-report=html
```

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture to validate against
- **[api.md](api.md)** — Interface definitions under test
- **[schemas/](schemas/)** — JSON Schema contracts used by validators
- **[roadmap.md](roadmap.md)** — Development phases with test milestones
