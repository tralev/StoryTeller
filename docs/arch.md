# StoryTeller Target Architecture and Data Format

## Document contract

This document specifies the intended implementation architecture and package
data model. It describes the target, not the current repository. Current status
is tracked by evidence-backed phase roadmap checkboxes. Behavioral flow belongs
in `design.md`.

## System boundaries

```text
Forge CLI (Python, local desktop)
  + future thin cross-platform/Wine launcher
  + local text, validation, image, and music backends
  + deterministic procedural simulation
  -> immutable .story v2

Native Player (Swift/iOS and Kotlin/Android)
  + package importer and reader
  + local MIDI playback
  + downloaded local llama.cpp GM model
  + app-private local saves
```

There is no StoryTeller server, account, remote API, telemetry pipeline, or
cloud-save subsystem.

## Forge layers

| Layer | Responsibility |
|---|---|
| CLI/application | Parse user intent and execute `GenerateStory` |
| Pipeline plan | Declare steps, dependencies, validation, checkpoints, failure policy, and model role |
| Procedural simulation | Produce authoritative physical, social, and historical domains |
| Narrative steps | Enrich the world, reconcile facts, write story/graph, direct art/music |
| Model adapters | Implement text, validator, image, and music protocols |
| Resource manager | Enforce RAM budget and mutually safe model lifetimes |
| Artifact repository | Typed, atomic, content-addressed artifact persistence |
| Checkpoints | Resume phase, sub-step, and node work after hash/fingerprint reconciliation |
| Packaging | Build deterministic v2 archive in staging |
| Acceptance | Validate archive exactly as a Player would before publication |
| Events | Emit versioned JSONL progress for CLI, logs, and GUI |

The application service is the only full-run entry point. CLI, overnight runner,
tests, and future GUI call it rather than assembling steps independently.

## Architectural vocabulary and ownership

StoryTeller uses several similar terms with different responsibilities:

| Term | Meaning | May know about |
|---|---|---|
| Interface/port | Capability required by core logic | Domain request/response types, lifecycle contract |
| Backend/adapter | Concrete implementation of one port | External library/model format and its configuration |
| Model file | Downloaded inference weights such as GGUF | Nothing; it is inert data loaded by a backend |
| Pipeline step | One deterministic unit in the generation DAG | Typed input artifacts, ports, validators, repository |
| Validator | Pure or model-assisted check returning structured issues | Schemas and relevant domain views; never storage side effects |
| Pipeline runner | Executes the validated plan | Policies, dependencies, checkpoints, events, cancellation |
| Application service | Owns one user use case | Run specification, runner, factories, final result |

The existing `src/models/` name refers mainly to pipeline steps, not downloaded
ML models. The target rewrite should move step implementations toward
`src/steps/` or make the distinction explicit. Downloaded weights remain outside
source control and are represented by `ModelDescriptor` values.

## Interfaces and ports

Core pipeline code depends on ports, never `llama_cpp`, Stable Diffusion,
`music21`, file-download clients, or platform UI directly.

```python
class TextGenerator(ManagedModel, Protocol):
    async def generate(self, request: TextRequest) -> JsonValue: ...

class ImageGenerator(ManagedModel, Protocol):
    async def generate_png(self, request: ImageRequest) -> bytes: ...

class MusicGenerator(Protocol):
    async def generate_score(self, request: MusicRequest) -> StructuredScore: ...
    def score_to_smf_type1(self, score: StructuredScore, *, ppq: int = 960) -> bytes: ...

class ArtifactRepository(Protocol):
    def commit_json(self, artifact: PendingJsonArtifact) -> ArtifactRef: ...
    def commit_bytes(self, artifact: PendingBinaryArtifact) -> ArtifactRef: ...

class EventSink(Protocol):
    def emit(self, event: DomainEvent) -> None: ...
```

Ports use typed domain requests so sampling parameters, seeds, expected schema,
and provenance cannot be hidden in arbitrary dictionaries.

## Validators

Validation is a pipeline of explicit, side-effect-free gates:

```text
candidate
  -> syntax/parse
  -> JSON Schema
  -> local domain invariants
  -> cross-artifact references
  -> world reconciliation or graph/media rules
  -> optional model critic
  -> normalized accepted artifact
```

Deterministic gates are mandatory. An optional model critic has four meaningful
states: valid, invalid, unavailable, and failed. Unavailable/failed never means
valid and never waives deterministic errors. Validators return stable issue
codes and JSON paths; the step decides whether retry policy permits another
candidate.

Target validator ownership:

| Validator | Scope |
|---|---|
| Schema validator | One serialized domain against its frozen schema |
| World invariant validator | Terrain through history internal correctness |
| World reconciler | Bible claims against immutable procedural facts |
| Narrative consistency validator | Story/graph identity, chronology, flags, endings |
| Media validator | PNG decode/profile/dimensions, score schema/timing, and score-derived MIDI parse/events/duration agreement |
| Package acceptance | Consumer-equivalent aggregate/security validation |

## Pipeline steps and runner

A step declares its artifact inputs/outputs, port role, validator chain,
checkpoint policy, and failure semantics in `PipelinePlan`. Its implementation
does only candidate generation and domain-specific transformation. The runner
owns orchestration concerns.

```python
@dataclass(frozen=True)
class StepSpec:
    step_id: str
    requires: tuple[ArtifactKey, ...]
    produces: ArtifactKey
    model_role: ModelRole | None
    validator_ids: tuple[str, ...]
    checkpoint: CheckpointPolicy
    failure: FailurePolicy
```

The runner resolves verified dependencies, acquires the backend/model resource,
executes bounded retries, validates and commits atomically, checkpoints the
`ArtifactRef`, emits events, and releases resources. Steps never directly mark
themselves complete.

## Backends and model files

`ProviderRegistry` maps strict configuration to backend factories. A backend is
responsible for translating a port request into one external engine call and
returning domain-neutral bytes/data. It does not select pipeline order, paths,
retry count, package fields, or acceptance policy.

| Port | Target backend responsibility | Candidate local engine/model |
|---|---|---|
| TextGenerator | Structured generation with explicit seed/sampling/schema | llama.cpp with verified Qwen GGUF |
| Validator critic | Independent bounded semantic critique | llama.cpp with verified Phi GGUF |
| ImageGenerator | PNG generation from complete prompt/seed/size | Stable Diffusion C++ with verified model |
| MusicGenerator | Structured score generation and deterministic SMF Type 1 rendering | text backend plus a pinned local score renderer |
| Mobile GmEngine | Chunked on-device answer generation | native llama.cpp with downloaded verified GGUF |

`ModelManager` owns load/unload and RAM admission. Only one incompatible heavy
model role is resident at a time. Model descriptors record repository, immutable
revision, filename, SHA-256, license/notice revision, role, quantization, context
limit, and expected memory. Paths and mutable download state are operational and
never part of canonical story content.

## Target pipeline plan

| Order | Step | Inputs | Output | Model role | Failure |
|---:|---|---|---|---|---|
| 1 | Procedural world | run specification | world domains | none | abort/resume |
| 2 | World Bible | all world domains | Bible | text | abort/resume |
| 3 | Reconciliation | world + Bible | reconciliation report | deterministic, optional critic | abort |
| 4 | Art direction | world + Bible | style Bible | text | abort |
| 5 | Story outline/chapters | world + Bible | story | text | abort/resume |
| 6 | Game design | world + Bible + story | graph | text | abort/resume |
| 7 | Music | graph | authoritative score + MIDI per node | text/converter | abort if either is missing |
| 8 | Images | graph + style | PNG + thumbnail per node | image | abort if any missing |
| 9 | GM indexing | all knowledge + graph | reveal-tagged index | none | abort |
| 10 | Manifest/package | every artifact | staged `.story` | none | abort |
| 11 | Acceptance/publish | staged package | published `.story` | none | abort |

Domain-separated seeds are derived from the master seed with a stable hash, not
by consuming one shared mutable RNG stream:

```python
def derive_seed(master: int, domain: str, item: str = "") -> int:
    value = f"storyteller:v2:{master}:{domain}:{item}".encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")
```

Domains include terrain, hydrology, climate, resources, regions,
civilizations, history, Bible, story, graph, each node image, and each node
music track.

## Procedural architecture

The generator is StoryTeller-owned and extends the existing `src/worldgen/`
code. It does not embed or invoke another world generator.

```text
RunSpec
 -> elevation + land/ocean
 -> hydrology (watersheds, rivers, lakes, coasts)
 -> climate (temperature, precipitation, seasons, weather regimes)
 -> biomes + natural resources
 -> regions + authoritative adjacency/routes
 -> sites + settlements
 -> civilizations + culture/government/economy
 -> year-by-year simulation
 -> final state + complete event ledger + snapshots at year 0, every 10 years, and final year
```

Default scope is one continent. Width, height, integer metres per world cell,
continent count, history length, and civilization limits are configurable.
Coordinates are integer cells `(x, y)`; distance is derived from
`metres_per_world_cell` without floating-point scale ambiguity.
Rendered maps are derived assets and never override structured facts.

Simulation stops at `present_year`. The final world is immutable thereafter.
The Bible may attach narrative-local entities to sites/regions but cannot mutate
authoritative domains.

## Reconciliation architecture

Reconciliation is a deterministic gate with an optional independent LLM critic.
Deterministic checks are mandatory and cannot be converted into warnings:

- Every major Bible location maps to a procedural region/site.
- Region coordinates, adjacency, route claims, climate, and resources agree.
- Civilizations preserve authoritative identity, territory, government, and
  chronological constraints.
- Bible events do not contradict the ledger or occur after `present_year` unless
  explicitly classified as narrative-present events.
- New local entities have a valid containing region/site.
- Story and graph references resolve through canonical artifact IDs.

An invalid Bible is retried from feedback; the world snapshot is never edited to
make the Bible pass.

## Typed composition

Canonical artifact keys, run specifications, graph nodes, choices, media
metadata, manifests, and checkpoint records are typed at composition boundaries.
JSON Schema remains the language-neutral authority at disk/package boundaries.

```python
@dataclass(frozen=True)
class RunSpec:
    seed: int
    title: str
    tone: str
    width: int = 1024
    height: int = 1024
    metres_per_world_cell: int = 8_000
    continent_count: int = 1
    history_years: int = 500
    civilization_count: int = 8

@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    path: str
    sha256: str
    depends_on: tuple[str, ...]
    producer_fingerprint: str
```

## Persistence and recovery

Every durable write follows serialize/generate -> validate -> fsync -> atomic
rename -> checkpoint. A checkpoint stores canonical path, content hash,
artifact ID, dependency IDs, producer fingerprint, seed, and attempts.

Resume performs reconciliation rather than trusting database presence:

1. Validate run specification and global fingerprint.
2. Verify the checkpoint's dependency IDs.
3. Verify file path is inside the run directory.
4. Hash and validate the actual file.
5. Reuse only if every check passes; otherwise invalidate downstream work.

Procedural history and long narrative phases checkpoint at deterministic
boundaries. Per-node image and score/MIDI work commits immediately. Mandatory
media failures may retry but never yield an accepted partial package.

## `.story` v1

Version 1 is the legacy narrative-first prototype. Its typical domains are
Bible, style Bible, story, graph, GM index, images, thumbnails, MIDI, and a
manifest. It may appear in fixtures and historical documentation only. Target
Forge and Player builds neither generate nor import v1.

## `.story` v2 status

Version 2 is the sole target product format. The structure below is the binding
target contract derived from product decisions. Its Draft 2020-12 schema dialect,
identities, package profile, shared-corpus approach, and three-validator boundary
are frozen; full field-level conformance is tracked by P8.C1–P8.C2. Future schema
changes follow the compatibility policy and must not discard these domains or
invariants.

## Frozen `.story` v2 layout

```text
<story>.story                 # deterministic ZIP, immutable
├── manifest.json
├── schemas/*.schema.json     # informational frozen bundle; bundled Player schemas are trusted
├── world/
│   ├── index.json            # scale, present year, domain paths and IDs
│   ├── terrain/index.json
│   ├── terrain/chunks/*.bin  # 256x256 surface chunks
│   ├── hydrology.json        # watersheds, rivers, lakes, coasts
│   ├── climate/index.json
│   ├── climate/chunks/*.bin
│   ├── biomes/index.json
│   ├── biomes/chunks/*.bin
│   ├── resources.json
│   ├── regions.json          # polygons/cells and adjacency
│   ├── routes.json
│   ├── sites.json
│   ├── civilizations.json
│   ├── history/index.json
│   ├── history/events/*.json # complete ordered causal event ledger
│   ├── history/snapshots/*.json
│   ├── local/index.json
│   └── local/<site-id>/      # index plus sparse 32x32x16 chunks for every site
│       ├── index.json
│       └── chunks/*.bin
├── narrative/
│   ├── bible.json
│   ├── reconciliation.json
│   ├── style_bible.json
│   ├── story.json
│   ├── graph.json
│   └── gm_index.json
└── assets/
    ├── maps/
    │   ├── world.png
    │   └── regions/<region-id>.png
    ├── images/<node-id>.png
    ├── thumbnails/<node-id>.png
    ├── music/<node-id>.score.json
    └── midi/<node-id>.mid
```

There is no `save/` directory. Reader state is external and app-private.

## v2 manifest core

```json
{
  "package_format": "storyteller.story",
  "package_version": 2,
  "story_id": "story_9f1c2d3e4a5b67890123456789abcdef",
  "title": "The Ashen Continent",
  "content_profile": "mature_dark_fantasy",
  "master_seed": 42,
  "entry_node": "node_00000000000000000000000000000001",
  "world": {
    "index": "world/index.json",
    "present_year": 500,
    "coordinate_system": "world_cell_xy",
    "metres_per_world_cell": 8000
  },
  "artifacts": [
    {
      "artifact_id": "terrain_a4b5c6d7e8f90123456789abcdef0123",
      "kind": "terrain",
      "path": "world/terrain/index.json",
      "sha256": "<64 lowercase hex>",
      "depends_on": [],
      "producer": {"component": "terrain", "version": "2", "fingerprint": "<sha256>"}
    }
  ],
  "node_assets": {
    "node_00000000000000000000000000000001": {
      "image": "assets/images/node_00000000000000000000000000000001.png",
      "thumbnail": "assets/thumbnails/node_00000000000000000000000000000001.png",
      "score": "assets/music/node_00000000000000000000000000000001.score.json",
      "midi": "assets/midi/node_00000000000000000000000000000001.mid"
    }
  },
  "content_hash": "<hash of canonical artifact inventory>"
}
```

Operational run time, local paths, RAM samples, retry history, and timestamps do
not affect canonical identity and do not belong in the immutable package unless
explicitly placed in a noncanonical diagnostics record.

Artifact IDs, `content_hash`, and `story_id` follow the exact non-circular
derivation in `package-v2.md`; implementations may not invent alternate identity
recipes. The ZIP container itself is never hashed.

## World-domain invariants

- All entity IDs are globally unique within a package and type-prefixed.
- Every world coordinate is within dimensions and uses integer cells.
- Every site belongs to a region; every route joins valid endpoints.
- Rivers follow hydrological topology; lakes/coasts reference terrain cells.
- Climate and biome records cover every relevant land cell or declared region.
- Resource occurrence is compatible with terrain/biome rules.
- Civilization ownership and population agree with snapshots at year 0, each
  ten-year boundary, and the final simulation year.
- Every event has stable ID, year, type, causes, participants, locations, and
  consequences; references resolve.
- Event order is stable by `(year, sequence, event_id)`.
- Every snapshot identifies the ledger position from which it derives.

## Narrative and media invariants

- Every major geographic/historical reference resolves to world data.
- Every node has at least one valid route or is a declared ending.
- Every choice target exists and flag conditions are coherent.
- Every node has exactly one full PNG, thumbnail PNG, authoritative structured
  score, and positive-duration SMF Type 1/960 PPQ MIDI derivative.
- The package contains a world map and one derived map for every region; map
  labels and geometry resolve to authoritative IDs and coordinates.
- Full PNG and thumbnail dimensions match manifest policy.
- GM index covers complete world and narrative knowledge.
- Every GM entry has `source_ids` and `reveal_after_nodes`.
- Runtime retrieval excludes entries whose reveal set is not satisfied by
  visited nodes before prompt assembly.

## Player architecture

Both native Players implement the same ports:

- `PackageValidator`: staged safe import and v2 acceptance
- `StoryRepository`: immutable package access
- `SaveRepository`: atomic app-private state keyed by story ID
- `MidiPlayer`: looping/crossfade playback
- `GmModelManager`: resumable verified first-launch model download and lifecycle
- `GmRetriever`: complete-index lookup plus strict visited-node filtering
- `GmEngine`: local chunk stream and cancellation

The iOS llama.cpp source checkout is third-party dependency code. StoryTeller
owns its small bridge and lifecycle contract, not upstream llama.cpp internals.

## Launcher architecture

The future GUI uses a toolkit selected later. Its stable boundary is process
based:

- Build an argument vector without shell interpolation.
- Start the packaged Forge executable.
- Read versioned JSONL events from stdout or an explicit event file.
- Send cancellation through a supported process signal/control action.
- Resume by invoking the same output directory.
- Display local model readiness, phase progress, errors, and final package path.

This keeps `win/`, `lin/`, and `mac/` packaging thin and prevents GUI/CLI
behavior drift.

## Security boundaries

Packages and model downloads are untrusted. Acceptance rejects unsafe paths,
links, undeclared entries, excessive decompression, schema violations, bad
hashes, provenance breaks, missing media, invalid PNG/MIDI, and unsupported v1.
Players stage extraction, validate, then atomically publish content read-only.

## Remaining product decisions

- Phase 8 selects the thin Wine-compatible GUI toolkit and semantic GM chunk and
  backpressure defaults.
- Phase 9 freezes the supported OS/device matrix and measured performance profiles.

These choices may alter representation, not the target domains or invariants.
