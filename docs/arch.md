# StoryTeller — Technical Architecture

## Core Architectural Pattern: JobQueue + PipelineStep

The Orchestrator dispatches phases through a JobQueue, which delegates execution to PipelineStep.run():

```
┌──────────────────────────────────────────────────────────────┐
│                    PIPELINE ARCHITECTURE                       │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Orchestrator (WHAT to run — phase ordering)                 │
│      │                                                        │
│      ▼                                                        │
│  ┌──────────┐                                                │
│  │JobQueue  │◄── Sequential: execute_step(step, ctx, id)      │
│  │          │◄── Parallel:  execute_parallel([(id,step),..])  │
│  └────┬─────┘                                                │
│       │                                                       │
│       ▼  (delegates to)                                       │
│  ┌──────────────────────────────────────────────┐            │
│  │  PipelineStep.run()                          │            │
│  │  Generator → Validator → Normalizer → Commit │            │
│  │  (with retry logic, MAX_RETRIES = 3)         │            │
│  └──────────────────────────────────────────────┘            │
│                                                               │
│  JobQueue adds: event logging, timing, failure tracking.      │
│  PipelineStep owns: the actual execution logic.               │
│  No duplication — one source of truth per concern.            │
└──────────────────────────────────────────────────────────────┘
```

**Why this matters:** The Orchestrator decides phase ordering (WHAT runs). The JobQueue handles dispatch (HOW it runs — sequential vs parallel, event logging). PipelineStep.run() owns the actual Gen→Val→Norm→Commit loop. Each concern has one implementation.

**Sequential vs parallel work:**
- **Sequential**: Text generation steps share one LLM — dispatched via `queue.execute_step()`
- **Parallel**: Image + music use different models — dispatched via `queue.execute_parallel()` using `asyncio.gather`

---

## Model Abstraction Layer

The pipeline never references specific models. Instead, it uses interfaces:

```python
class TextGenerator(Protocol):
    """Generates structured text output from prompts."""
    async def generate(self, prompt: str, schema: dict) -> dict: ...
    async def generate_stream(self, prompt: str) -> AsyncIterator[str]: ...

class Validator(Protocol):
    """Validates generated content against rules and schemas."""
    async def validate(self, content: dict, context: dict) -> ValidationResult: ...

class ImageGenerator(Protocol):
    """Generates images from text prompts."""
    async def generate(self, prompt: str, size: tuple) -> bytes: ...

class MusicGenerator(Protocol):
    """Generates ABC notation from scene descriptions."""
    async def generate(self, scene: dict, mood: str) -> str: ...

class GameMaster(Protocol):
    """Answers reader questions with context-aware responses."""
    async def answer(self, question: str, context: dict) -> AsyncIterator[str]: ...
```

**Concrete implementations** are mapped through configuration:

```yaml
# config/models.yaml
generators:
  text:
    provider: llama_cpp
    model: qwen2.5-7b-instruct
    quantization: Q4_K_M
  validator:
    provider: llama_cpp
    model: phi-3.5-mini-instruct
    quantization: Q4_K_M
  image:
    provider: stable_diffusion_cpp
    model: sdxl-turbo
    quantization: Q8_0
  music:
    provider: abc_notation  # LLM generates ABC, music21 converts to MIDI
  game_master:
    provider: llama_cpp
    model: llama-3.2-3b-instruct
    quantization: Q4_K_M
```

Swapping models requires changing only this file. No code changes, no doc updates.

---

## Technology Stack

### App B — The Forge (Desktop)

| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.9+ | Mature ML ecosystem, cross-platform, PyInstaller-packable |
| **Job Queue** | `asyncio` + `JobQueue.execute_step` / `execute_parallel` | Lightweight, delegates to PipelineStep, event logging |
| **LLM Inference** | `llama-cpp-python` | CPU-optimized GGUF inference, streaming, Python bindings |
| **Image Generation** | `stable-diffusion-cpp-python` | CPU-only Stable Diffusion via C++ bindings |
| **MIDI Conversion** | `music21` | Pure Python ABC→MIDI conversion |
| **JSON Validation** | `jsonschema` + `pydantic` | Schema enforcement and data modeling |
| **Prompt Templates** | `jinja2` | Version-controlled, composable prompt management |
| **Checkpoint/State** | `sqlite3` (stdlib) | Zero-config persistent pipeline state and resume |
| **Packaging** | `zipfile` (stdlib) + `PyInstaller` | `.story` archive builder; single-executable distribution |
| **Determinism** | `json.dumps(sort_keys=True)` + fixed float precision + reproducibility profile | Same-machine reproducible output |

### App A — The Player (Mobile)

| Layer | iOS | Android |
|---|---|---|
| **Language** | Swift 5.9+ | Kotlin 2.0+ |
| **UI Framework** | SwiftUI | Jetpack Compose |
| **LLM Inference** | `llama.cpp` Swift bindings | `llama.cpp` JNI bindings |
| **MIDI Playback** | `AVAudioEngine` + bundled SoundFont | `MediaPlayer` + bundled SoundFont |
| **Image Display** | `AsyncImage` / `Nuke` | `Coil` |
| **Data Format** | `Codable` JSON parsing | `kotlinx.serialization` |

---

## Project Structure

```
StoryTeller/
├── docs/                           # All documentation
│   ├── goal.md
│   ├── arch.md
│   ├── design.md
│   ├── roadmap.md
│   ├── test.md
│   ├── readme.md
│   ├── api.md                      # Interface definitions
│   └── schemas/                    # JSON Schema contracts
│       ├── bible.schema.json
│       ├── style_bible.schema.json
│       ├── story.schema.json
│       ├── graph.schema.json
│       ├── gm_index.schema.json
│       └── manifest.schema.json
├── forge/                          # App B — The Forge
│   ├── pyproject.toml
│   ├── config/
│   │   └── models.yaml             # Model→interface mapping
│   ├── src/
│   │   ├── __init__.py
│   │   ├── job_queue.py            # JobQueue dispatch + PipelineContext + FailurePolicy
│   │   ├── config.py               # Paths, model settings, constants
│   │   ├── cli.py                  # CLI entry point (forge generate, etc.)
│   │   ├── normalizer.py           # Enforces conventions on all output
│   │   ├── application/            # Application service layer (Phase 5.5A)
│   │   │   ├── __init__.py
│   │   │   ├── models.py           # GenerationRequest, GenerationResult
│   │   │   └── generate_story.py   # GenerateStory service (shared CLI + overnight)
│   │   ├── pipeline/               # Pipeline infrastructure (Phase 5.5F,H)
│   │   │   ├── __init__.py
│   │   │   ├── errors.py           # Structured error taxonomy
│   │   │   ├── events.py           # Typed domain events
│   │   │   └── batch.py            # BatchScheduler + NodeJob
│   │   ├── interfaces/             # Model abstraction interfaces
│   │   │   ├── __init__.py
│   │   │   ├── text_generator.py
│   │   │   ├── validator.py
│   │   │   ├── image_generator.py
│   │   │   ├── music_generator.py
│   │   │   └── game_master.py
│   │   ├── cli.py                  # CLI entry point (forge generate, etc.)
│   │   ├── normalizer.py           # Enforces conventions on all output
│   │   ├── artifact_store.py       # Streaming write-through artifact storage
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Abstract PipelineStep
│   │   │   ├── bible_helpers.py    # Shared Bible summarization helper
│   │   │   ├── world_builder.py    # Step 1
│   │   │   ├── story_writer.py     # Step 2
│   │   │   ├── game_designer.py    # Step 3 (incremental)
│   │   │   ├── art_director.py     # Step 4
│   │   │   ├── image_generator_step.py  # Step 5a (parallel)
│   │   │   └── music_generator_step.py  # Step 5b (parallel)
│   │   ├── validators/
│   │   │   ├── __init__.py
│   │   │   ├── schema_validator.py
│   │   │   ├── graph_validator.py
│   │   │   ├── cross_ref_checker.py
│   │   │   ├── consistency.py
│   │   │   └── composite.py        # DeterministicValidator (schema+cross_ref+graph+consistency)
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   ├── llm_backend.py     # Concrete TextGenerator + Validator
│   │   │   ├── image_backend.py   # Concrete ImageGenerator
│   │   │   ├── midi_backend.py    # ABC→MIDI converter
│   │   │   ├── gm_backend.py      # Concrete GameMaster (stub)
│   │   │   └── model_manager.py   # Shared lifecycle + RAM budget
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── checkpoint.py      # SQLite state
│   │   │   ├── packager.py        # Deterministic .story ZIP builder
│   │   │   ├── orchestrator.py    # Pipeline scheduler
│   │   │   ├── indexer.py         # GM inverted index builder
│   │   │   ├── manifest_builder.py # Manifest generation (Phase 5.5D)
│   │   │   ├── package_acceptance.py # .story acceptance gate (Phase 5.5D)
│   │   │   └── artifact_store.py  # Streaming write-through storage
│   │   └── prompts/               # Versioned Jinja2 templates
│   │       ├── world_builder_v1.j2
│   │       ├── story_writer_v1.j2
│   │       ├── game_designer_v1.j2
│   │       ├── art_director_v1.j2
│   │       ├── composer_v1.j2
│   │       ├── game_master_v1.j2
│   │       ├── style_bible_v1.j2
│   │       └── consistency_check_v1.j2
│   ├── scripts/
│   │   ├── run_overnight.py       # Overnight test runner
│   │   ├── dry_run.py             # Mock end-to-end test (8 phases)
│   │   ├── verify_streaming.py    # ArtifactStore write-through verification
│   │   ├── pull_models.sh         # Model download script (4 GGUF models)
│   │   └── run_docker.sh          # Docker convenience wrapper
│   └── tests/
├── droid/                          # App A — Android Player (Kotlin)
├── ios/                            # App A — iOS Player (Swift)
├── mac/                            # Native macOS launcher (future)
└── windows/                        # Native Windows launcher (future)
```

---

## Versioning: Every Artifact

Every JSON artifact produced by the pipeline carries version metadata:

```json
{
  "schema_version": 1,
  "generator_version": "0.4.1",
  "pipeline_version": 7,
  "created_at": "2026-08-03T14:22:00Z",
  "model_versions": {
    "text_generator": "qwen2.5-7b-instruct-q4_k_m",
    "validator": "phi-3.5-mini-instruct-q4_k_m",
    "image_generator": "sdxl-turbo-q8_0",
    "music_generator": "via-text"
  },
  "prompt_versions": {
    "world_builder": "v1",
    "style_bible": "v1",
    "story_writer": "v2",
    "game_designer": "v1",
    "art_director": "v1",
    "composer": "v1"
  },
  "seed": 1234567890,
  "generation_params": {
    "tone": "dark_fantasy",
    "title": "The Ashen Marches",
    "temperature": 0.7,
    "node_count": 15
  }
}
```

This is present in: `bible.json`, `story.json`, `graph.json`, `style_bible.json`, `manifest.json`, `gm_index.json`.

Each artifact also carries a globally unique `artifact_id` (e.g., `world_a1b2c3d4`, `story_e5f6g7h8`, `package_i9j0k1l2`). Artifacts reference each other by ID, not by filename. The manifest records the full dependency chain:

```json
{
  "artifact_id": "package_i9j0k1l2",
  "depends_on": [
    {"artifact_id": "world_a1b2c3d4", "type": "world_bible"},
    {"artifact_id": "story_e5f6g7h8", "type": "linear_story"},
    {"artifact_id": "graph_m3n4o5p6", "type": "cyoa_graph"}
  ]
}
```

This enables provenance tracking, cache invalidation, and future tooling that needs to trace an asset back to its origin.

**Why:** If the schema evolves (v1 → v2), the mobile app can detect the version and either handle both formats or show an "update your app" message. If a story was generated with an older model, the metadata tells you exactly which one. The `reproducibility_profile` records the hardware/config needed to reproduce the output. The `prompt_versions` record exactly which prompt template version produced each artifact — enabling A/B comparison when prompt templates evolve.

---

## Prompt Templates as Versioned Assets

Prompts are first-class versioned artifacts, stored in `forge/src/prompts/`:

```
# Current (v1):
prompts/
├── world_builder_v1.j2
├── art_director_v1.j2
├── story_writer_v1.j2
├── game_designer_v1.j2
├── composer_v1.j2
├── game_master_v1.j2
├── style_bible_v1.j2
└── consistency_check_v1.j2

# Aspirational — future versions when prompts evolve:
# prompts/
# ├── world_builder_v2.j2
# ├── story_writer_v2.j2
# ├── story_writer_v3.j2
```

Every generated artifact records which prompt version produced it. When a prompt is revised, the version is bumped. Old prompt files are never deleted — they're needed to reproduce old artifacts. The pipeline resolves prompt versions from the artifact's `prompt_versions` metadata, not from a global "latest" pointer.

---

## Event Log

In addition to the SQLite checkpoint (which tracks pipeline *state*), an append-only event log records every action for debugging:

```jsonl
{"timestamp": "2026-08-03T12:10:00Z", "type": "step_started", "step_id": "world_builder", "artifact_id": "world_a1b2c3d4"}
{"timestamp": "2026-08-03T12:13:22Z", "type": "validation_failed", "step_id": "world_builder", "errors": ["missing required field: magic_system.source"]}
{"timestamp": "2026-08-03T12:13:23Z", "type": "step_retrying", "step_id": "world_builder", "attempt": 2}
{"timestamp": "2026-08-03T12:15:41Z", "type": "step_completed", "step_id": "world_builder", "artifact_id": "world_a1b2c3d4", "duration_seconds": 341}
```

Written to `pipeline_events.jsonl` in the output directory. Appended, never overwritten. Invaluable for debugging 24-hour runs — you can `tail -f` it during generation or grep it after a failure.

---

## Pipeline State vs Project State

The pipeline maintains two distinct categories of data:

| Category | What | Storage | Lifecycle |
|---|---|---|---|
| **Pipeline State** | Checkpoints, retry counts, event log, loaded models | SQLite DB + `pipeline_events.jsonl` | Ephemeral — deleted after successful run |
| **Project** | Bible, story, graph, images, MIDI, .story package | Output directory | Permanent — the product |

Pipeline state exists only to enable resumption and debugging. It is never part of the deliverable. The project is what ships. Keeping them separate means: delete the checkpoint DB to force a clean restart; archive the output directory to preserve the product; the two never interfere.

---

## Game Master Spoiler Prevention

To prevent the Game Master from revealing future plot points, entities in the World Bible carry an optional `reveal_after_node` field:

```json
{
  "id": "char_05",
  "name": "The Betrayer",
  "reveal_after_node": "node_12",
  "description": "The trusted ally who..."
}
```

On mobile, when assembling the GM prompt:
1. The `gm_index.json` entity_cache includes `reveal_after_node` for gated entities
2. Before injecting an entity summary, the app checks: has the reader visited `reveal_after_node` (or any node beyond it)?
3. If not, the entity is excluded from the GM's context — the GM literally doesn't know about it
4. Entities without `reveal_after_node` are always available (basic world knowledge)

This is enforced **structurally** — not by prompting the LLM to "avoid spoilers" but by withholding the information entirely.

---

## Partial-Failure Handling

For a pipeline that may run 24+ hours, aborting on any failure is unacceptable. Pipeline steps support **quarantine mode**:

```python
class FailurePolicy(Enum):
    ABORT = "abort"           # Stop entire pipeline (default for sequential phases)
    QUARANTINE = "quarantine"  # Skip failed item, continue with others (default for parallel phases)
```

When a per-node generation fails in QUARANTINE mode:
- The node is skipped (no placeholder — it simply isn't in the output)
- The pipeline continues processing remaining nodes
- At the end, if ALL nodes failed, a `RuntimeError` is raised
- If some nodes succeeded, the pipeline reports: "14/15 nodes complete"

This means a single stuck image generation doesn't waste 23 hours of completed work.

---

## Deterministic .story Output

Given the same seed, same models, **same machine, and same configuration** (thread count, quantization, CPU architecture), the `.story` file will be **reproducible** (bit-identical on that machine).

> ⚠️ **Cross-machine determinism is not guaranteed.** llama.cpp and stable-diffusion.cpp use multi-threaded CPU inference where floating-point matrix multiplication order varies by thread count and CPU architecture. This is a known limitation, not a bug. The guarantee is: reproduce the same output on the same hardware.

A `reproducibility_profile` is recorded in every artifact:

```json
{
  "reproducibility_profile": {
    "cpu_arch": "arm64",
    "thread_count": 4,
    "quantization": "Q4_K_M",
    "llama_cpp_version": "b4567",
    "os": "darwin"
  }
}
```

| Mechanism | Implementation |
|---|---|
| Sorted JSON keys | `json.dumps(data, sort_keys=True, indent=2)` |
| Fixed float precision | All floats rounded to 6 decimal places before serialization |
| Deterministic ZIP | Entries sorted alphabetically; timestamps normalized to `1980-01-01 00:00:00` |
| Stable prompts | Seed passed to LLM sampler; temperature fixed |
| Normalized IDs | Entity IDs generated deterministically from seed, not from LLM |
| Reproducibility profile | CPU arch, thread count, quantization recorded in metadata |

**Why:** Enables hashing, caching, and diffing on the same machine. If you regenerate the same story on the same hardware and get a different file, that's a bug. Cross-machine reproducibility is not guaranteed — see reproducibility_profile for the required config to match.

---

## Immutable Content vs Mutable State

The `.story` package separates content that never changes from data created by the reader:

```
story.story
├── content/                  # IMMUTABLE — never changes after generation
│   ├── manifest.json
│   ├── bible.json
│   ├── style_bible.json
│   ├── story.json
│   ├── graph.json
│   ├── gm_index.json
│   ├── images/
│   ├── midi/
│   └── thumbnails/
└── save/                     # MUTABLE — created and updated by the reader
    ├── save_state.json       # current_node, flags, visited_nodes
    ├── gm_history.json       # past Game Master conversations
    └── bookmarks.json        # user bookmarks
```

On the mobile app:
- `content/` is read-only after import
- `save/` is written to the app's private storage
- Cloud sync only syncs `save/` — the content is already on the device

---

## Reproducibility via Seeds

Every generation stage records its seed and parameters:

```
Seed (user-provided or random)
    │
    ▼
World Bible  ← seed propagated, recorded in bible.json
    │
    ▼
Story        ← seed propagated, recorded in story.json
    │
    ▼
Branches     ← seed propagated, recorded in graph.json
    │
    ▼
Images       ← seed propagated to SDXL sampler
    │
    ▼
Music        ← seed propagated to LLM sampler
```

If a user preserves their models and the seed, they can regenerate the exact same book years later by running:

```bash
forge generate --seed 1234567890 --title "The Ashen Marches" --tone dark_fantasy
```

---

## The Normalizer

Between validation and commit, every output passes through a **Normalizer**:

```
Generator → Validator → Normalizer → Commit
```

The Normalizer enforces project-wide conventions:

| Rule | Example |
|---|---|
| Entity ID format | `char_01`, not `character1` or `c1` |
| Consistent naming | `dark_fantasy`, not `Dark Fantasy` or `dark-fantasy` |
| Sorted arrays | All entity arrays sorted by `id` |
| Whitespace | No trailing spaces, single newline at EOF |
| JSON formatting | 2-space indent, sorted keys |
| Asset references | Paths use forward slashes, relative to content root |
| Flag names | `snake_case`, no spaces or special chars |

This gives every downstream component (and the mobile app) a predictable input format.

---

## Related Documents

- **[design.md](design.md)** — Behavioral design: pipeline flows, UX flows, block diagrams
- **[api.md](api.md)** — Interface definitions for all model roles, config spec, CLI reference
- **[schemas/](schemas/)** — JSON Schema contracts between pipeline stages
- **[roadmap.md](roadmap.md)** — Development phases and milestones
- **[test.md](test.md)** — Test strategy and test cases

---

## Core Data Schemas (See `docs/schemas/`)

JSON schemas are the **single source of truth** for all data structures. They live in `docs/schemas/` and are authoritative. Prose descriptions in this document and others are illustrative only. If there is a conflict between prose and schema, the schema wins.

Every validator imports these schemas directly. Every generator prompt includes the relevant schema as part of its instructions. No data structure is described in two places.

| Schema | Validates |
|---|---|
| `bible.schema.json` | World Bible structure, entity types, cross-references |
| `style_bible.schema.json` | Art style constraints |
| `story.schema.json` | Linear story structure, chapter/scene hierarchy |
| `graph.schema.json` | CYOA graph, nodes, choices, flags, endings |
| `gm_index.schema.json` | Inverted index, entity cache, node contexts |
| `manifest.schema.json` | .story manifest, version metadata, file inventory |

---

## Coding Patterns

### 1. JobQueue Dispatch

```python
class JobQueue:
    async def execute_step(self, step, context, job_id) -> StepOutput:
        self._log_event("step_started", job_id)
        output = await step.run(context)  # delegates to PipelineStep
        self._log_event("step_completed", job_id)
        return output

    async def execute_parallel(self, steps, context) -> list:
        tasks = [self.execute_step(s, ctx, jid) for jid, s in steps]
        return await asyncio.gather(*tasks, return_exceptions=True)

# Orchestrator dispatches phases through the queue
class Orchestrator:
    async def run(self, seed: int) -> PipelineContext:
        queue = JobQueue(event_log_path="pipeline_events.jsonl")
        # Sequential phases
        for name in ["world_builder", "art_director", "story_writer", "game_designer"]:
            await queue.execute_step(self.steps[name], context, name)
        # Parallel phase
        await queue.execute_parallel(
            [("image", img_step), ("music", mus_step)], context
        )
        # Finalize
        for name in ["indexer", "packager"]:
            await queue.execute_step(self.steps[name], context, name)
```

### 2. Model Interface

```python
class TextGenerator(Protocol):
    provider: str
    model_name: str
    quantization: str
    
    async def generate(self, prompt: str, schema: dict) -> dict: ...
    async def generate_stream(self, prompt: str) -> AsyncIterator[str]: ...
    async def load(self) -> None: ...
    async def unload(self) -> None: ...
```

### 3. Schema Validation with Retry Feedback

```python
class SchemaValidator:
    def validate(self, data: dict, schema_name: str) -> ValidationResult:
        schema = load_schema(f"docs/schemas/{schema_name}.schema.json")
        errors = Draft7Validator(schema).iter_errors(data)
        if errors:
            return ValidationResult(
                is_valid=False,
                errors=[self._format_error(e) for e in errors],
                retry_prompt=f"Your JSON had these errors: {errors}. Fix them."
            )
        return ValidationResult(is_valid=True)
```

### 4. Normalizer Pipeline

```python
class Normalizer:
    @classmethod
    def process(cls, data: dict) -> dict:
        data = cls.normalize_entity_ids(data)
        data = cls.normalize_enums(data)
        data = cls.normalize_flag_names(data)
        data = cls.normalize_asset_paths(data)
        data = cls.sort_arrays(data)
        data = cls.normalize_json(data)
        data = cls.normalize_whitespace(data)
        return data
```
