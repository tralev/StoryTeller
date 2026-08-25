# StoryTeller Target API and Contract Reference

## Scope

This future-facing reference covers every public boundary: Forge Python ports,
CLI, launcher events, `.story` v2, and native Player behavior. Internal helper
classes belong in `arch.md`; delivery belongs in the phase roadmaps here.

Names may be introduced incrementally, but released behavior must remain
compatible with these contracts.

## Python application API

```python
@dataclass(frozen=True)
class GenerationRequest:
    seed: int
    title: str
    tone: Literal["mature_dark_fantasy"]
    output_dir: Path
    config_path: Path | None = None
    resume: bool = False
    width: int = 1024
    height: int = 1024
    metres_per_world_cell: int = 8_000
    continent_count: int = 1
    history_years: int = 500
    civilization_count: int = 8


@dataclass(frozen=True)
class GenerationResult:
    status: Literal["complete", "cancelled", "failed"]
    run_id: str
    story_id: str | None
    package_path: Path | None
    content_hash: str | None
    errors: tuple[ErrorRecord, ...]


class GenerateStory:
    async def execute(self, request: GenerationRequest) -> GenerationResult: ...
```

`execute` is the only supported whole-pipeline entry point. A successful result
always names a published, accepted v2 package.

## Model ports

```python
class ManagedModel(Protocol):
    async def load(self) -> None: ...
    async def unload(self) -> None: ...
    @property
    def ram_usage_mb(self) -> int: ...


@dataclass(frozen=True)
class TextRequest:
    prompt: str
    schema: Mapping[str, object]
    seed: int
    temperature_ppm: int
    max_tokens: int


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    width: Literal[1024]
    height: Literal[1024]
    seed: int


@dataclass(frozen=True)
class MusicRequest:
    node_id: str
    scene_summary: str
    mood: str
    culture_ids: tuple[str, ...]
    location_ids: tuple[str, ...]
    seed: int


@dataclass(frozen=True)
class Beat:
    numerator: int
    denominator: int


@dataclass(frozen=True)
class ScoreEvent:
    event_id: str
    kind: Literal["note", "chord", "rest", "control", "pitch_bend"]
    start: Beat
    duration: Beat
    pitches: tuple[int, ...] = ()
    velocity: int | None = None
    value: int | None = None


@dataclass(frozen=True)
class ScoreTrack:
    track_id: str
    role: str
    gm_program: int | None
    drum_channel: bool
    events: tuple[ScoreEvent, ...]


@dataclass(frozen=True)
class StructuredScore:
    schema_version: Literal["storyteller.score.v1"]
    node_id: str
    ppq: Literal[960]
    duration: Beat
    tempo_map: tuple[Mapping[str, JsonValue], ...]
    time_signature_map: tuple[Mapping[str, JsonValue], ...]
    key_signature_map: tuple[Mapping[str, JsonValue], ...]
    tracks: tuple[ScoreTrack, ...]
    markers: Mapping[Literal["INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START"], Beat]
    source_ids: tuple[str, ...]
    producer_fingerprint: str
    expected_midi_sha256: str


class TextGenerator(ManagedModel, Protocol):
    async def generate(self, request: TextRequest) -> JsonValue: ...


class Validator(ManagedModel, Protocol):
    async def validate(
        self, content: Mapping[str, object], context: ValidationContext,
    ) -> ValidationResult: ...


class ImageGenerator(ManagedModel, Protocol):
    async def generate_png(self, request: ImageRequest) -> bytes: ...


class MusicGenerator(Protocol):
    async def generate_score(self, request: MusicRequest) -> StructuredScore: ...
    def score_to_smf_type1(self, score: StructuredScore, *, ppq: int = 960) -> bytes: ...
```

Backends return bytes/data; pipeline storage owns paths and atomic publication.
Every `Beat` is reduced, has a positive denominator, and maps exactly to a 960-PPQ
tick: `(numerator * 960) % denominator == 0`. Events are ordered by start tick,
event kind, pitch tuple, then event ID. Pitches are `0..127`, sounding velocities
are `1..127`, duration is positive, markers are monotonic and within duration,
and `LOOP_START < LOOP_END`. The renderer emits track 0 conductor metadata, then
one track per declared score track in tuple order. Simultaneous MIDI events use
the frozen priority note-off, program/control, pitch-bend, note-on. The score is
first rendered without consulting `expected_midi_sha256`; that full MIDI hash is
then stored in the final authoritative score and verified during acceptance.

## Procedural ports

```python
@dataclass(frozen=True)
class WorldGenerationSpec:
    master_seed: int
    width: int
    height: int
    metres_per_world_cell: int
    continent_count: int
    history_years: int
    civilization_count: int


class WorldGenerator(Protocol):
    def generate(self, spec: WorldGenerationSpec) -> WorldArtifacts: ...


class WorldReconciler(Protocol):
    def validate(
        self, world: WorldArtifacts, bible: Bible,
    ) -> ReconciliationReport: ...
```

`WorldArtifacts` exposes separate terrain, hydrology, climate, biomes,
resources, regions, sites, civilizations, history, and snapshot domains.

## Artifact repository

```python
@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    canonical_path: str
    sha256: str
    depends_on: tuple[str, ...]
    producer_fingerprint: str


class ArtifactRepository(Protocol):
    def put_json(self, kind: ArtifactKey, value: JsonValue) -> ArtifactRef: ...
    def put_bytes(self, kind: ArtifactKey, path: str, value: bytes) -> ArtifactRef: ...
    def load_verified(self, ref: ArtifactRef) -> JsonValue | bytes: ...
    def exists_verified(self, ref: ArtifactRef) -> bool: ...
```

Writes are same-directory atomic. Verification includes path confinement, hash,
schema/media validity, and dependency fingerprint.

## Validation result

```python
@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Literal["error", "warning"]
    path: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    status: Literal["valid", "invalid", "unavailable", "failed"]
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.status == "valid" and not any(
            issue.severity == "error" for issue in self.issues
        )
```

Deterministic validator unavailability is terminal. Optional critic
unavailability is recorded but cannot convert invalid content to valid.

## Error contract

Every externally visible error contains:

```json
{
  "code": "PACKAGE_MEDIA_MISSING",
  "category": "package",
  "message": "Node node_00000000000000000000000000000007 has no MIDI asset",
  "retryable": false,
  "step_id": "package_acceptance",
  "item_id": "node_00000000000000000000000000000007",
  "details": {}
}
```

Stable categories are `configuration`, `dependency`, `resource`, `generation`,
`validation`, `persistence`, `package`, `download`, and `cancelled`.

## CLI

```text
forge generate [options]
forge resume --output DIR [--config PATH]
forge validate-package PACKAGE [--json]
forge inspect-package PACKAGE [--json]
forge download-models [--role ROLE] [--models-dir DIR]
forge models list [--json]
forge models verify [--config PATH] [--role ROLE]
forge info --output DIR [--json]
forge cancel --output DIR
```

Target `generate` options:

```text
--seed INTEGER                    required or explicit generated seed
--title TEXT
--tone mature_dark_fantasy
--output DIR
--config PATH
--world-width INTEGER
--world-height INTEGER
--metres-per-world-cell INTEGER
--continents INTEGER              default 1
--history-years INTEGER
--max-civilizations INTEGER
--workers INTEGER
--fresh                           refuse/recreate run state explicitly
--events PATH                     JSONL event destination
--json-result                     emit final result as JSON
```

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Successful accepted package or successful query/validation |
| 2 | CLI/configuration error |
| 3 | Dependency/model unavailable or invalid |
| 4 | Generation/validation exhausted |
| 5 | Persistence/package acceptance failure |
| 130 | User cancellation |

CLI stdout is human-readable unless `--json-result` is selected. Diagnostics go
to stderr. JSONL events go only to their declared stream/path.

## Launcher process contract (P8.10)

The GUI passes an argument vector to Forge and consumes versioned JSONL events
on stdout (or a `--events PATH` file). Every event is a single valid JSON line.

### JSONL envelope

Every line shares these fields:

```json
{
  "event_version": 1,
  "sequence": 104,
  "timestamp": "2026-08-04T12:00:00Z",
  "run_id": "run_<id>",
  "type": "step_progress"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `event_version` | int | JSONL format version (currently `1`). Bumped on incompatible change. |
| `sequence` | int | Monotonic, starting at 1 per run. Gaps mean lines were dropped. |
| `timestamp` | string | ISO 8601 UTC. |
| `run_id` | string | Stable run identifier. |
| `type` | string | Event type (see below). Unknown types **must** be ignored. |

### Line limits

Maximum line length (including trailing `\n`): **4,096 bytes**. Longer lines are
truncated with a `...}` sentinel. Truncation emits a warning to stderr.

### Malformed / partial / unknown event handling

- **Malformed line** (not valid JSON): skipped. Emit a single warning to stderr
  containing the byte offset, never the raw line content (may contain sentinels).
- **Partial line** (no trailing `\n` at EOF): discarded. Consumer waits for `\n`
  or EOF before processing.
- **Unknown `type`**: ignored silently. Forward compatibility requires tolerance.
- **Missing required field** (`type`, `sequence`, `run_id`): skipped with warning.
- **Duplicate sequence**: the later event replaces the earlier one.

### stdout vs stderr ownership

| Stream | Contents |
|--------|----------|
| **stdout** | JSONL events (when `--json-result` is active) or human-readable output |
| **stderr** | Diagnostics, warnings, truncation notices, progress messages |

JSONL events are never interleaved on stderr. The launcher reads exclusively
from the declared `--events PATH` file or stdout pipe.

### Event types

| Type | When emitted | Key fields |
|------|-------------|------------|
| `pipeline_started` | Run begins | `seed`, `title`, `tone` |
| `reuse_summary` | Resume start (P8.10) | `reused_count`, `regenerated_count`, `total_artifacts` |
| `model_loading` | Model load begins | `model_name`, `estimated_mb` |
| `model_loaded` | Model ready | `model_name`, `ram_mb` |
| `model_unloaded` | Model released | `model_name` |
| `step_started` | Step begins | `step_id`, `attempt` |
| `step_progress` | In-step progress (P8.10) | `step_id`, `completed`, `total`, `message` |
| `step_completed` | Step succeeded | `step_id`, `artifact_key`, `duration_s` |
| `step_failed` | Step failed | `step_id`, `error_code`, `error_message`, `retryable` |
| `step_retrying` | Step retrying | `step_id`, `attempt`, `feedback` |
| `artifact_committed` | Artifact saved | `step_id`, `artifact_key`, `artifact_id` |
| `artifact_reused` | Artifact from prior run (P8.10) | `step_id`, `artifact_key`, `artifact_id`, `reused_from_run` |
| `artifact_regenerated` | Artifact regenerated (P8.10) | `step_id`, `artifact_key`, `artifact_id`, `reason` |
| `validation_failed` | Validator rejected content | `step_id`, `error_count`, `errors` |
| `item_quarantined` | Single item quarantined | `step_id`, `item_id`, `reason` |
| `checkpoint_saved` | Checkpoint written | `step_id`, `phase` |
| `pipeline_cancelled` | User cancelled | `cancelled_at` |
| `pipeline_failed` | Fatal error | `errors` |
| `pipeline_completed` | Success | `package_path`, `content_hash`, `total_duration_s` |

`pipeline_completed` includes the final accepted package path and content hash.
`pipeline_cancelled` is distinct from `pipeline_failed`: cancellation is
external, not an internal error.

### P8.10: Artifact reuse / regeneration

On resume, Forge emits a `reuse_summary` event **before** any step runs:

```json
{
  "event_version": 1,
  "sequence": 3,
  "timestamp": "2026-08-06T08:00:00Z",
  "run_id": "run_abc123",
  "type": "reuse_summary",
  "reused_count": 14,
  "regenerated_count": 3,
  "total_artifacts": 17
}
```

This allows the launcher to explain why verification may be slow ("3 artifacts
regenerated because dependencies changed") without exposing hidden content or
scraping human logs.

During execution, every committed artifact emits either `artifact_reused` or
`artifact_regenerated`. Aggregate counts are available at any time from the
event log without re-parsing the entire file.

### Cancellation acknowledgement

When the launcher sends SIGINT or the `forge cancel` command, Forge:

1. Sets the cancellation flag.
2. Allows the current step to reach its next commit boundary (no partial artifacts).
3. Emits `pipeline_cancelled`.
4. Exits with code 130.

The launcher must not assume immediate termination. It reads events until
`pipeline_cancelled` or `pipeline_completed` appears.

### Resume command

```text
forge resume --output DIR [--config PATH]
```

Resume reopens the output directory's checkpoint database, replays the event
log to reconstruct state, and continues from the last committed step.

### Stable diagnostic envelope

Every error-bearing event uses the same error envelope as the global error
contract (see above). Stable codes never change meaning; new codes may be
added.

## `.story` v1 contract

v1 is documented only as the legacy narrative-first prototype. Target commands
and Players return `PACKAGE_UNSUPPORTED_VERSION` for v1. No migration API is
provided.

## `.story` v2 contract

The normative directory contract is specified in `package-v2.md`; these
invariants are binding before and after executable schemas are generated:

- ZIP paths are UTF-8, relative, `/`-separated, unique, and sorted.
- ZIP entry timestamps and permissions are normalized.
- `manifest.json` is at archive root and declares every file.
- All JSON is UTF-8, canonicalized, finite-number-only, and schema-valid.
- JSON uses RFC 8785 JCS and JSON Schema Draft 2020-12.
- Entity/artifact IDs use `<type>_<32 lowercase hex>`; SHA-256 fields use all 64
  lowercase hexadecimal characters.
- Sorted, duplicate-free `required_features` and `optional_features` implement
  feature negotiation; unknown required features are rejected.
- World data is split into domain files and is complete.
- All references use stable IDs, never implicit display-name matching.
- Every node declares image, thumbnail, authoritative score, and MIDI paths.
- The manifest declares a world map and one derived map for every region.
- No save or conversation data exists inside the package.
- No executable content, HTML, scripts, models, or undeclared extension exists.

Manifest acceptance API:

```python
class PackageAcceptance(Protocol):
    def validate(self, package: Path) -> PackageAcceptanceResult: ...

@dataclass(frozen=True)
class PackageAcceptanceResult:
    accepted: bool
    package_version: int | None
    story_id: str | None
    content_hash: str | None
    issues: tuple[ValidationIssue, ...]
```

Acceptance checks path safety before extraction, then entry limits, manifest,
versions, schemas, inventory, hashes, provenance, cross-references, node media
coverage, decoded PNG dimensions, score/MIDI agreement, MIDI profile/duration, and
unknown files.

## World history event contract

```json
{
  "event_id": "event_00000000000000000000000000001234",
  "year": 317,
  "sequence": 4,
  "type": "war_started",
  "causes": ["event_00000000000000000000000000001198"],
  "participants": ["civ_00000000000000000000000000000003", "civ_00000000000000000000000000000007"],
  "locations": ["region_00000000000000000000000000000012"],
  "consequences": [
    {"kind": "diplomacy", "subject": "civ_00000000000000000000000000000003", "value": "at_war:civ_00000000000000000000000000000007"}
  ],
  "summary": "The Salt War began after the eastern route collapsed."
}
```

Events are ordered by year, sequence, and ID. Causes reference earlier events.

## GM index and retrieval contract

```json
{
  "entry_id": "knowledge_00000000000000000000000000001234",
  "kind": "event",
  "normalized_text": "the salt war began after the eastern route collapsed",
  "source_ids": ["event_00000000000000000000000000001234", "civ_00000000000000000000000000000003", "region_00000000000000000000000000000012"],
  "incoming_refs": [],
  "outgoing_refs": [],
  "reveal_after_nodes": ["node_00000000000000000000000000000008"]
}
```

The retrieval algorithm is versioned by the Player/Forge contract. It takes two
independent identity inputs, which must not be conflated:

- `visited_nodes: set[str]` — graph node IDs the reader has reached. Drives the
  reveal gate and the recency boost (step 5f).
- `visited_refs: set[str]` — the union of `authoritative_refs` (world-entity
  source IDs) across every node in `visited_nodes`. Drives the visited/
  containment boosts (steps 5f–5g). A Player computes this by looking up each
  visited node's `authoritative_refs` in the packaged graph and unioning them;
  it is never itself a set of node IDs.

Steps:

1. Apply the reveal gate to the raw entry sequence. An entry is eligible only
   when every ID in `reveal_after_nodes` is in the visited-node set; an empty
   requirement is eligible. Rejected entries leave this boundary before any
   searchable string, score, diagnostic, or prompt line is constructed. The
   gate preserves input order and does not log rejected IDs, source IDs, or text.
2. Normalize the query and searchable entry fields with Unicode NFKC and
   locale-independent lowercase.
3. Replace each run of non-letter/non-digit characters with one space, trim,
   split, remove duplicates, and sort query tokens lexicographically.
4. Search `kind`, `normalized_text`, and `source_ids`.
5. Compute an integer score as the sum of every feature that applies:
   a. **Kind weight** — a fixed base score per `entry.kind`: `creature` 200,
      `person` 180, `opportunity` 160, `event` 150, `civilization` 140,
      `settlement` 130, `site` 120, `location` 120, `region` 110, `route` 100,
      `artifact` 100, `local_map` 90, `graph_node` 80, `story_scene` 70,
      `bible_local` 60, `ecology` 50, `registries` 40, `identities` 40,
      `cohort` 40; any other kind defaults to 50. An entry with zero matching
      query tokens (step 5b) scores `0` overall and is dropped, regardless of
      kind weight.
   b. **Token match** — `100 *` the count of distinct query tokens present in
      the searchable text.
   c. **Exact phrase** — `+500` when the complete normalized query is a
      substring of the searchable text.
   d. **Exact source** — `+400` when any query token equals one of
      `entry.source_ids` verbatim.
   e. **Current node** — only when `current_node_id` is given: `+300` if it is
      in `entry.reveal_after_nodes`; `+150` if it is in `entry.outgoing_refs`.
      Both may apply.
   f. **Visited** — only when `visited_refs` is non-empty: `+200` if
      `entry.source_ids` intersects `visited_refs`; `+100` if
      `entry.outgoing_refs` intersects `visited_refs`. Both may apply.
   g. **Containment** — only when `visited_refs` is non-empty: `+250` if
      `entry.outgoing_refs ∪ entry.incoming_refs` intersects `visited_refs`.
      Independent of, and additive with, 5f.
   h. **Recency** — only for an entry whose `reveal_after_nodes` intersects
      `visited_nodes`: rank every ID in `visited_nodes` by descending
      lexicographic sort (rank `0` = last alphabetically, not last visited —
      `visited_nodes` is an unordered set and carries no chronology); take the
      entry's minimum rank among the IDs it shares with `visited_nodes`, then
      add `max(0, 50 - 10 * rank)`.
6. Sort by descending integer score and then ascending `entry_id`.
7. Format a candidate as `[entry_id] (kind) normalized_text`. Select whole lines
   in rank order while their UTF-8 byte cost, including inter-line newlines, fits
   `context_budget_bytes`; skip an oversized line and continue. Stop at
   `max_results`.

The defaults are a 4,096-byte context budget and eight results. Empty queries,
zero budgets, and entries with score zero return no result. `current_node_id`
and `visited_refs` are optional; omitting both reduces scoring to kind weight
plus token/phrase/source features only. The executable cross-platform fixtures,
including scenarios exercising every boost above, are in
`tests/fixtures/gm_retrieval/catalog.json`.

Eligibility rule:

```python
def revealed(entry: KnowledgeEntry, visited: set[str]) -> bool:
    required = set(entry.reveal_after_nodes)
    return not required or required.issubset(visited)
```

Reveal filtering runs before ranking or prompt assembly. A debug/test-only API
may expose eligible or selected IDs. Production UI, logs, errors, saved history,
and local diagnostics must not expose rejected IDs, source IDs, or text. Both
Players must produce identical eligible entry IDs for the same package, question
normalization, current node, and visited-node set.

## GM chunk stream

Platform adapters expose equivalent semantics:

```text
start(question, context) -> stream<Chunk>
Chunk = Started | Text(text) | Completed(full_text, usage) | Failed(error)
cancel(request_id) -> acknowledgement
```

Text chunks contain non-empty ordered substrings, not necessarily model tokens.
Only a completed assistant message is persisted unless the shared behavior
contract later explicitly adopts marked partial messages.

## Local save contract

```json
{
  "save_version": 1,
  "story_id": "story_9f1c2d3e4a5b67890123456789abcdef",
  "package_content_hash": "<sha256>",
  "playthrough_id": "<local uuid>",
  "current_node": "node_00000000000000000000000000000004",
  "visited_nodes": ["node_00000000000000000000000000000001", "node_00000000000000000000000000000004"],
  "flags": {"spared_witch": true},
  "bookmarks": [],
  "gm_history": [
    {"role": "user", "text": "Who built this keep?"},
    {"role": "assistant", "text": "..."}
  ]
}
```

Saves are atomic, app-private, never embedded into `.story`, never synchronized,
and isolated with a clear error when their package identity does not match.

## Player import result

Both platforms expose the conceptual result:

```text
IMPORTED(story_id)
ALREADY_IMPORTED(story_id)
UNSUPPORTED_VERSION(found=1, supported=2)
INVALID_PACKAGE(error_codes...)
INSUFFICIENT_STORAGE(required_bytes...)
CANCELLED
```

No v1 migration state exists. Platform-specific UI text may vary while these
outcomes remain identical.

## Compatibility policy

- Forge v2 emits only package version 2.
- Player v2 imports only package version 2.
- Additive schema changes require sorted declared feature flags and reader tolerance;
  unknown required features are rejected and unknown optional behavior is ignored.
- Breaking changes require a new package version and an explicit product
  decision; silent coercion is forbidden.
- Exact v2 JSON Schemas are executable authorities and must remain synchronized
  with `package-v2.md`, shared fixtures, and all three validators.
