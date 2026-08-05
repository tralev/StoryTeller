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

## Launcher process contract

The GUI passes an argument vector to Forge and consumes schema-versioned events:

```json
{
  "event_version": 1,
  "sequence": 104,
  "timestamp": "2026-08-04T12:00:00Z",
  "run_id": "run_<id>",
  "type": "step_progress",
  "step_id": "history_simulation",
  "completed": 300,
  "total": 500,
  "message": "Simulated year 300 of 500"
}
```

Required event types: `pipeline_started`, `model_loading`, `model_loaded`,
`step_started`, `step_progress`, `artifact_committed`, `step_retrying`,
`checkpoint_saved`, `step_completed`, `pipeline_cancelled`, `pipeline_failed`,
and `pipeline_completed`.

Events are append-only, sequence-numbered, valid single-line JSON, and safe to
ignore when unknown. `pipeline_completed` includes final path and hashes.

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
  "entry_id": "knowledgeevent_00000000000000000000000000001234",
  "kind": "event",
  "normalized_text": "the salt war began after the eastern route collapsed",
  "source_ids": ["event_00000000000000000000000000001234", "civ_00000000000000000000000000000003", "region_00000000000000000000000000000012"],
  "incoming_refs": [],
  "outgoing_refs": [],
  "reveal_after_nodes": ["node_00000000000000000000000000000008"]
}
```

The retrieval algorithm is versioned by the Player/Forge contract:

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
5. Score `100` for each distinct exact query-token hit and add `500` when the
   complete normalized query is a substring of the searchable text.
6. Sort by descending integer score and then ascending `entry_id`.
7. Format a candidate as `[entry_id] (kind) normalized_text`. Select whole lines
   in rank order while their UTF-8 byte cost, including inter-line newlines, fits
   `context_budget_bytes`; skip an oversized line and continue. Stop at
   `max_results`.

The defaults are a 4,096-byte context budget and eight results. Empty queries,
zero budgets, and entries with score zero return no result. The executable
cross-platform fixtures are in `tests/fixtures/gm_retrieval/catalog.json`.

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
