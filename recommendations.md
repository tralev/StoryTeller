# StoryTeller Hardening Roadmap

## Purpose

This is a self-contained implementation roadmap for closing the remaining gaps
between StoryTeller's design and its current code. It is written for incremental
delivery: every task has a stable ID, target files, and an observable completion
condition. Code blocks are starting points that should be adapted alongside the
existing tests rather than pasted blindly.

## Current baseline

Verified on 2026-08-04:

- [x] `GenerateStory` is the shared generation/resume entry point.
- [x] Package acceptance runs before a generated package is published.
- [x] Phase and per-node SQLite checkpoints exist.
- [x] Resume rejects whole-run fingerprint mismatches.
- [x] `PipelinePlan` and `ExecutionPolicy` exist.
- [x] JSON artifacts and final `.story` publication use atomic replacement.
- [x] Pipeline events and cancellation cleanup exist.
- [x] Forge, Android, and iOS use canonical `.story` fixtures.
- [x] `mypy src scripts tests` passes for 121 files.
- [ ] `pytest -q` is fully green: current result is 815 passed and 4 failed.
  One failure is archive determinism; three are model-dependent smoke tests.

## Delivery order

```text
Y determinism gate
  -> N typed contracts
  -> O atomic media + recovery
  -> P node retry/quarantine
  -> Q coverage policy
  -> R binary acceptance
  -> X provenance
  -> S/T cross-platform contracts
  -> G Game Master proof
  -> V generated documentation
  -> U operational acceptance
```

N through R and X should land before changing the package schema. S and T then
lock that schema across readers. U is the release-candidate gate.

---

## Y. Canonical Determinism Gate

**Problem:** two fake-backed runs with the same seed and configuration currently
produce different normalized manifests. Canonical output must not depend on the
output directory, wall clock, creation order, or random IDs.

**Target files:** `src/storage/content_hash.py`,
`src/storage/manifest_builder.py`, `src/storage/packager.py`,
`tests/test_phase56d.py`.

- [ ] **Y1:** Make the failing test print the first mismatching archive path and
  JSON pointer rather than only the final manifest diff.
- [ ] **Y2:** Classify every manifest field as canonical or operational.
- [ ] **Y3:** Exclude output paths, timestamps, durations, and run-local IDs from
  canonical hashes.
- [ ] **Y4:** Derive canonical artifact IDs only from normalized content.
- [ ] **Y5:** Require two same-seed archives to have identical canonical entry
  bytes and content hashes.

Suggested diagnostic helper:

```python
from __future__ import annotations

import zipfile
from pathlib import Path


def first_archive_difference(left: Path, right: Path) -> tuple[str, bytes, bytes] | None:
    with zipfile.ZipFile(left) as a, zipfile.ZipFile(right) as b:
        names = sorted(set(a.namelist()) | set(b.namelist()))
        for name in names:
            av = a.read(name) if name in a.namelist() else b"<missing>"
            bv = b.read(name) if name in b.namelist() else b"<missing>"
            if av != bv:
                return name, av, bv
    return None
```

**Done when:**

```bash
.venv/bin/pytest -q tests/test_phase56d.py
```

passes repeatedly and from two different temporary output directories.

---

## N. Type Composition Boundaries

**Problem:** composition relies on `dict[str, Any]`, string artifact keys, a
non-generic `StepOutput`, and request values copied into
`PipelineContext.state`.

**Target files:** `src/models/base.py`, `src/job_queue.py`,
`src/application/models.py`, `src/artifact_store.py`, `src/pipeline/plan.py`.

- [ ] **N1:** Add `ArtifactKey` as an enum or `Literal` for canonical artifacts.
- [ ] **N2:** Make `StepOutput[T]` generic.
- [ ] **N3:** Add `TypedDict` or dataclass boundary models for Manifest,
  GraphNode, Choice, image metadata, and MIDI metadata.
- [ ] **N4:** Put the immutable `GenerationRequest` on `PipelineContext` instead
  of copying title, tone, and temperature into `state`.
- [ ] **N5:** Add typed repository methods for high-value artifacts.
- [ ] **N6:** Remove obsolete string-key maps once all callers use one canonical
  mapping.

Starting point:

```python
# src/pipeline/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar, TypedDict


class ArtifactKey(StrEnum):
    WORLD_SNAPSHOT = "world_snapshot"
    BIBLE = "bible"
    STYLE_BIBLE = "style_bible"
    STORY = "story"
    GRAPH = "graph"
    IMAGES = "images"
    MIDI = "midi"
    GM_INDEX = "gm_index"
    PACKAGE_PATH = "package_path"


class Choice(TypedDict):
    text: str
    target_node: str


class GraphNode(TypedDict):
    node_id: str
    text: str
    choices: list[Choice]
    image_path: str
    midi_path: str


PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True)
class StepOutput(Generic[PayloadT]):
    data: PayloadT
    step_name: str
    artifact_id: str | None = None
    validator_status: str | None = None
```

Context migration:

```python
@dataclass
class PipelineContext:
    run_id: str
    seed: int
    request: GenerationRequest
    # Keep state temporarily for operational/transient extension data only.
    state: dict[str, object] = field(default_factory=dict)

# Before: ctx.state["temperature"]
# After:  ctx.request.temperature
```

**Done when:** `rg 'state\["(title|tone|temperature)"\]' src` returns no
matches and mypy rejects an invalid graph choice or artifact key.

---

## O. Atomic Persistence and Recovery

**Problem:** JSON and final package writes are atomic, but image/MIDI publication
and the node checkpoint are not a recoverable, verified pair.

**Target files:** `src/artifact_store.py`, image/music step modules,
`src/storage/checkpoint.py`, `src/pipeline/batch.py`.

- [x] **O1:** Write JSON output through a same-directory temporary file.
- [ ] **O2:** Write image and MIDI output to a temporary path and atomically
  rename only after successful validation.
- [ ] **O3:** Store canonical path, SHA-256, producer fingerprint, artifact ID,
  and attempt count in every node checkpoint.
- [ ] **O4:** Reconcile checkpoint metadata against actual bytes during resume.
- [x] **O5:** Publish final `.story` only after `PackageAcceptance` succeeds.
- [ ] **O6:** Add crash-window tests for artifact-before-checkpoint and
  checkpoint-before-artifact failures.
- [ ] **O7:** Flush file data before rename where a power-loss durability
  guarantee is required.

Reusable atomic byte writer:

```python
# src/storage/atomic.py
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, destination)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
```

Checkpoint schema direction:

```sql
ALTER TABLE node_checkpoints ADD COLUMN canonical_path TEXT NOT NULL DEFAULT '';
ALTER TABLE node_checkpoints ADD COLUMN content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE node_checkpoints ADD COLUMN producer_fingerprint TEXT NOT NULL DEFAULT '';
ALTER TABLE node_checkpoints ADD COLUMN artifact_id TEXT NOT NULL DEFAULT '';
```

Resume must verify bytes, not existence:

```python
def checkpoint_matches(path: Path, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    return sha256(path.read_bytes()).hexdigest() == expected_sha256
```

For large media, replace `read_bytes()` with chunked hashing.

**Done when:** killing a worker between rename and checkpoint commit never causes
corrupt output or an invalid skip on resume.

---

## P. Per-Node Retry and Quarantine

**Problem:** successful node output is checkpointed, but quarantine is a string
map, per-node attempts are not driven through a complete policy loop, and resume
accepts a checkpoint primarily on path existence.

**Target files:** `src/pipeline/batch.py`, `src/pipeline/errors.py`,
`src/pipeline/policy.py`, `src/storage/checkpoint.py`.

- [x] **P1:** Integrate `BatchScheduler` with `CheckpointStore`.
- [x] **P2:** Checkpoint each successful image immediately.
- [x] **P3:** Checkpoint each successful MIDI immediately.
- [ ] **P4:** Persist structured quarantine records with stable error codes.
- [ ] **P5:** Schedule only missing, invalid, or fingerprint-mismatched nodes on
  resume.
- [ ] **P6:** Apply `ExecutionPolicy.max_retries` to each node.
- [ ] **P7:** Verify worker counts 1 and N produce identical canonical results.
- [ ] **P8:** Propagate terminal errors; quarantine only independent retryable
  generation/validation failures.

Suggested contract:

```python
@dataclass(frozen=True)
class QuarantineRecord:
    node_id: str
    step_name: str
    code: str
    message: str
    attempts: int
    retryable: bool


async def run_with_policy(job: NodeJob, worker: Worker[T], policy: ExecutionPolicy) -> T:
    total_attempts = policy.max_retries + 1  # retries exclude first attempt
    for attempt in range(1, total_attempts + 1):
        try:
            return await worker(job)
        except StoryTellerError as exc:
            if not exc.retryable or attempt == total_attempts:
                raise
    raise AssertionError("unreachable")
```

**Done when:** tests prove retry counts, terminal-error behavior, quarantine
scope, resume filtering, and concurrency-independent output.

---

## Q. Asset Coverage Policy

**Problem:** quarantined assets can result in a structurally valid but incomplete
package. Product policy must decide whether that package is rejected or accepted
with warnings.

**Target files:** `src/config.py`, `config/models.yaml`,
`src/storage/manifest_builder.py`, `src/storage/package_acceptance.py`,
`src/application/models.py`, `src/cli.py`.

- [ ] **Q1:** Define each asset class as required, optional, or threshold-based.
- [ ] **Q2:** Add configurable image and MIDI minimum coverage.
- [ ] **Q3:** Record expected, generated, missing, and quarantined counts in the
  manifest.
- [ ] **Q4:** Enforce coverage in `PackageAcceptance`.
- [ ] **Q5:** Report `complete`, `incomplete_accepted`, and `rejected` distinctly.

Configuration example:

```yaml
pipeline:
  asset_coverage:
    images:
      required: true
      minimum: 1.0
    midi:
      required: false
      minimum: 0.8
```

```python
@dataclass(frozen=True)
class CoverageRule:
    required: bool = True
    minimum: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum <= 1.0:
            raise ValueError("minimum coverage must be between 0 and 1")


def coverage(generated: int, expected: int) -> float:
    return 1.0 if expected == 0 else generated / expected
```

Manifest example:

```json
{
  "asset_stats": {
    "images": {"expected": 15, "generated": 15, "missing": [], "quarantined": []},
    "midi": {"expected": 15, "generated": 13, "missing": ["node_08", "node_12"], "quarantined": ["node_08"]}
  }
}
```

**Done when:** acceptance results and CLI exit behavior are deterministic for
100%, threshold-passing, threshold-failing, and zero-expected cases.

---

## R. Binary Asset Acceptance

**Problem:** an existing archive path does not prove that an image decodes or a
MIDI track can play.

**Target files:** `src/storage/package_acceptance.py`,
`tests/test_story_fixtures.py`, `scripts/generate_story_fixtures.py`.

- [ ] **R1:** Decode every PNG and reject corrupt payloads.
- [ ] **R2:** Verify full image and thumbnail dimensions.
- [ ] **R3:** Parse every MIDI and reject corrupt or empty tracks.
- [ ] **R4:** Require positive MIDI duration.
- [ ] **R5:** Add corrupt PNG, wrong-dimension PNG, truncated MIDI, and
  zero-duration MIDI fixtures.
- [ ] **R6:** Bound decompression size to avoid ZIP/image bombs.

PNG check using Pillow:

```python
from io import BytesIO
from PIL import Image, UnidentifiedImageError


def validate_png(payload: bytes, expected: tuple[int, int]) -> str | None:
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
        with Image.open(BytesIO(payload)) as image:
            if image.format != "PNG" or image.size != expected:
                return f"expected PNG {expected}, got {image.format} {image.size}"
    except (UnidentifiedImageError, OSError) as exc:
        return f"invalid PNG: {exc}"
    return None
```

MIDI check using the already-used `music21` dependency:

```python
import tempfile
from pathlib import Path
from music21 import converter


def midi_duration_seconds(payload: bytes) -> float:
    if not payload.startswith(b"MThd"):
        raise ValueError("missing MIDI header")
    with tempfile.NamedTemporaryFile(suffix=".mid") as tmp:
        tmp.write(payload)
        tmp.flush()
        score = converter.parse(Path(tmp.name))
        return float(score.seconds)
```

**Done when:** every malformed fixture is rejected with a stable issue path and
code, while all canonical fixtures remain accepted.

---

## W. Policy Semantics Tests

**Problem:** policy fields exist, but exact retry and failure behavior must be a
public, tested contract.

**Target files:** `src/pipeline/policy.py`, `src/models/base.py`,
`src/pipeline/batch.py`, `tests/test_phase56g.py` or a new focused test module.

- [ ] **W1:** Define `max_retries` as attempts after the first call; total
  attempts are `max_retries + 1`.
- [ ] **W2:** Never retry configuration, unavailable-resource, or persistence
  errors.
- [ ] **W3:** Retry generation/validation errors exactly according to policy.
- [ ] **W4:** Apply QUARANTINE only to independent item jobs.
- [ ] **W5:** Always abort on missing dependencies and storage failures.

Minimal parameterized test shape:

```python
@pytest.mark.parametrize(
    ("error", "max_retries", "expected_calls"),
    [
        (GenerationError("temporary"), 2, 3),
        (ConfigurationError("bad config"), 2, 1),
        (PersistenceError("disk full"), 2, 1),
    ],
)
async def test_attempt_contract(error, max_retries, expected_calls):
    worker = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await execute_with_policy(worker, ExecutionPolicy(max_retries=max_retries))
    assert worker.await_count == expected_calls
```

Use the repository's actual error constructors/codes when implementing the test.

---

## X. Artifact Provenance

**Problem:** the run fingerprint answers “does this whole run match?” but not
“which exact inputs produced this artifact?”

**Target files:** artifact schemas, `src/storage/checkpoint.py`,
`src/storage/manifest_builder.py`, `src/storage/package_acceptance.py`.

- [ ] **X1:** Store canonical artifact IDs in artifact envelopes or inventory.
- [ ] **X2:** Record `depends_on`: Bible -> Story -> Graph -> Assets/Index ->
  Package.
- [ ] **X3:** Record model, prompt, schema, and producer hashes per artifact.
- [ ] **X4:** Use dependency IDs/hashes for targeted resume invalidation.
- [ ] **X5:** Validate provenance consistency during package acceptance.
- [ ] **X6:** Version the envelope and provide a migration path for old packages.

Canonical ID helper:

```python
import hashlib
import json
from typing import Any


def canonical_artifact_id(kind: str, payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{kind}_{digest[:24]}"
```

Envelope example:

```json
{
  "artifact_id": "graph_12ab34cd56ef...",
  "kind": "graph",
  "schema_version": 1,
  "depends_on": ["bible_abcd...", "story_ef01..."],
  "producer": {
    "model_sha256": "...",
    "prompt_sha256": "...",
    "code_version": "..."
  },
  "payload": {}
}
```

**Done when:** changing the Bible invalidates Story and downstream artifacts but
does not invalidate unrelated assets, and acceptance rejects broken dependency
references.

---

## S. Shared Cross-Platform Contract Scenarios

**Problem:** sharing fixture archives does not prove Forge, Android, and iOS
interpret them identically.

**Target files:** `tests/fixtures/story_packages/`, Android/iOS test resources,
fixture generation script, all three acceptance/import test suites.

- [ ] **S1:** Create one machine-readable scenario catalog.
- [ ] **S2:** Verify entry point, node count, choices, flags, endings, and media
  paths against that catalog on all platforms.
- [ ] **S3:** Require identical rejection categories for path traversal, missing
  manifest, bad references, hash mismatch, and corrupt media.
- [ ] **S4:** Verify identical `reveal_after_node` spoiler gating.
- [ ] **S5:** Generate/copy fixtures from one command and fail CI on drift.

Scenario example:

```json
{
  "scenario_version": 1,
  "cases": [
    {
      "id": "valid_minimal_v1",
      "archive": "minimal_valid_1_node.story",
      "accepted": true,
      "entry_point": "node_01",
      "node_count": 1
    },
    {
      "id": "invalid_path_traversal_v1",
      "archive": "invalid_path_traversal.story",
      "accepted": false,
      "error_code": "PACKAGE_UNSAFE_PATH"
    }
  ]
}
```

**Done when:** CI executes the same scenario IDs in Python, Android, and iOS and
fails on any outcome mismatch.

---

## T. Mobile Package-Version Behavior

**Problem:** schema upgrades need explicit, equivalent outcomes on both readers.

- [ ] **T1:** Distinguish supported, older-migratable, newer-unsupported, and
  corrupt packages on Android.
- [ ] **T2:** Implement the same states and user-facing meaning on iOS.
- [ ] **T3:** Add shared old/new/migration fixtures.
- [ ] **T4:** Keep mutable save state outside immutable imported content.
- [ ] **T5:** Define migration ownership, transactional rollback, and backup
  behavior before schema v2.

Shared conceptual result:

```text
SUPPORTED(version)
MIGRATION_REQUIRED(from_version, to_version)
UNSUPPORTED_NEWER(found_version, max_supported)
CORRUPT(error_code)
```

**Done when:** both apps produce the same conceptual result for every version
fixture, even if their platform-specific UI text differs.

---

## G. Game Master Streaming and Spoiler Isolation

**Problem:** mobile streaming code exists, but package-to-prompt spoiler
isolation, download recovery, latency, and memory behavior lack shared evidence.

- [ ] **G1:** Test that unrevealed GM entries never enter retrieval output or the
  model prompt.
- [ ] **G2:** Test partial model download, checksum failure, cancellation, and
  offline restart on Android and iOS.
- [ ] **G3:** Measure time to first token and peak RAM on representative devices.
- [ ] **G4:** Decide whether the Python GM backend participates in the contract;
  test it or explicitly mark it out of scope.
- [ ] **G5:** Ensure streaming cancellation releases the model and file handles.

Security-oriented test shape:

```python
visible = build_gm_context(index, visited_nodes={"node_01"})
assert "node_01" in visible.source_node_ids
assert "node_09" not in visible.source_node_ids
assert "secret ending" not in visible.prompt.lower()
```

**Done when:** spoiler checks operate on the final prompt input, not merely UI
visibility, and device measurements are recorded.

---

## V. Documentation Drift Prevention

**Problem:** hand-maintained pipeline tables, CLI options, archive paths, and test
counts drift from executable behavior.

- [ ] **V1:** Generate the phase/artifact table from `PipelinePlan.standard()`.
- [ ] **V2:** Snapshot CLI help from the argparse parser.
- [ ] **V3:** Test documented archive paths against
  `PackageAcceptance.REQUIRED_ENTRIES` and related constants.
- [ ] **V4:** Generate volatile counts or remove them.
- [ ] **V5:** Label features as implemented, partial, planned, or operationally
  verified.

Generation sketch:

```python
def pipeline_markdown(plan: PipelinePlan) -> str:
    rows = ["| Step | Output | Requires | Model |", "|---|---|---|---|"]
    for step in plan:
        rows.append(
            f"| `{step.id}` | `{step.output_key}` | "
            f"{', '.join(step.requires) or '-'} | {step.model_role or '-'} |"
        )
    return "\n".join(rows) + "\n"
```

Generate between explicit markers so narrative documentation remains hand-owned.

**Done when:** CI regenerates contract-derived documentation and fails if the
working tree changes.

---

## U. Operational Acceptance

**Problem:** fake-backed coverage is broad, but release claims require real-model,
container, resume, and device evidence.

- [ ] **U1:** Mark real-model tests as provisioned integration tests and skip
  with an exact setup instruction when a model is absent.
- [ ] **U2:** Fix or document the current Qwen llama-context allocation failure.
- [ ] **U3:** Record one controlled real-model Bible-to-package run with model,
  prompt, configuration, and toolchain hashes.
- [ ] **U4:** Measure load/unload order, peak RAM, and duration.
- [ ] **U5:** Interrupt and resume a real run; compare canonical output with an
  uninterrupted run.
- [ ] **U6:** Build the Docker image and run a containerized dry run.
- [ ] **U7:** Verify downloaded models against pinned SHA-256 values.
- [ ] **U8:** Import one production-generated package on physical Android and iOS
  devices.

Acceptance record template:

```yaml
run_id: acceptance-YYYY-MM-DD-01
git_commit: "<sha>"
platform: "macOS <version>, <CPU>, <RAM>"
python: "<version>"
models:
  text:
    file: Qwen2.5-7B-Instruct-Q4_K_M.gguf
    sha256: 65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423
result:
  content_hash: "<sha>"
  duration_seconds: 0
  peak_ram_mb: 0
resume_equivalent: false
android_imported: false
ios_imported: false
```

Do not commit private machine paths or secrets in the acceptance record.

**Done when:** a versioned acceptance record links to logs and hashes for a
successful real-model package imported by both mobile readers.

---

## Phase Definition of Done

- [ ] `forge generate` produces a schema-valid, accepted `.story` or exits
  non-zero.
- [x] Package acceptance always runs through the application service.
- [ ] Manifest identity, inventory, binary media, provenance, and hashes are
  complete and verified.
- [x] Resume works through `GenerateStory`.
- [x] Unsafe whole-run checkpoints are rejected by run fingerprint.
- [ ] Resume validates each node's file hash and producer fingerprint.
- [ ] Interrupted and uninterrupted runs produce identical canonical results.
- [ ] Every configured execution policy changes runtime behavior and is tested.
- [x] Strict mypy reports zero errors across `src`, `scripts`, and `tests`.
- [ ] The default non-provisioned test suite is fully green.
- [ ] One real-model end-to-end run is recorded.
- [x] Android and iOS consume the same canonical package fixtures.
- [ ] Android and iOS pass the same behavior scenarios.
- [ ] Documentation is generated from executable contracts where practical.

## Recommended verification commands

```bash
.venv/bin/mypy src scripts tests
.venv/bin/pytest -q -m "not integration"
.venv/bin/pytest -q tests/test_phase56d.py
.venv/bin/pytest -q tests/test_story_fixtures.py
```

Provisioned model verification:

```bash
STORYTELLER_MODELS_DIR="$PWD/ai_models" \
  .venv/bin/pytest -q -m integration tests/test_real_model_smoke.py
```

Run platform tests through their existing project commands after S/T scenario
adapters are added; CI should treat any cross-platform outcome mismatch as a
contract failure.
