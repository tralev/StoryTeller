# Rewrite Phase 1: Contracts and Repository Foundations

## Mission

Replace the mixed v1 composition layer with a typed, deterministic v2-ready
foundation. This phase does not define `.story` v2 and does not delete v1
schemas. Temporary end-to-end breakage is allowed; the foundation tests below
must pass.

## Entry state audit

| Current area | Disposition | Reason |
|---|---|---|
| `src/application/generate_story.py` | Rewrite orchestration boundary | It mixes context construction, factories, lifecycle, resume, and finalization |
| `src/application/models.py` | Replace request/result contracts | Procedural settings are incomplete and narrative/procedural modes must disappear |
| `src/pipeline/artifacts.py` | Retain concepts, rewrite types | Useful typed start, but v2 world/provenance contracts are not represented |
| `src/pipeline/plan.py` | Retain and generalize | Declarative execution is the correct direction |
| `src/job_queue.py` and `src/storage/orchestrator.py` | Consolidate | Execution ownership remains split |
| `src/config.py` | Rewrite as strict domain config | Current dataclasses do not cover authoritative world generation or media requirements |
| `src/pipeline/errors.py`, `events.py`, `policy.py` | Retain, normalize | Stable errors/events/policy are valuable but need one public contract |
| v1 schemas, prompts, packager, mobile | Keep temporarily | Removed only after v2 freeze in Phase 6 |

## Target boundary

```text
CLI / future GUI
  -> GenerateStory.execute(GenerationRequest)
  -> validated RunSpec
  -> PipelineRunner.run(PipelinePlan, RunContext)
  -> typed ArtifactRepository + CheckpointRepository + EventSink
```

No pipeline step reads CLI objects or arbitrary `state` keys. One runner owns
dependency checks, retry policy, cancellation, checkpoint commits, and events.

## Action plan

- [ ] **P1.1 (M, no dependencies):** Add `src/domain/` with `run_spec.py`,
  `artifacts.py`, `errors.py`, and JSON value aliases. Move canonical contracts
  out of execution modules.
- [ ] **P1.2 (M, depends P1.1):** Replace `GenerationRequest` with mandatory
  procedural fields and remove `world_mode`. Default to one continent.
- [ ] **P1.3 (M, depends P1.1):** Define domain-separated seed derivation and a
  versioned `SeedPlan`; prohibit shared mutable RNG across domains.
- [ ] **P1.4 (L, depends P1.1):** Replace string output maps with typed
  `ArtifactKey`, `ArtifactRef`, and repository methods.
- [ ] **P1.5 (L, depends P1.2,P1.4):** Introduce `RunContext` containing frozen
  `RunSpec`, repositories, event sink, and cancellation token. Remove generation
  values from `PipelineContext.state`.
- [ ] **P1.6 (XL, depends P1.5):** Consolidate `JobQueue` and `Orchestrator` into
  `src/pipeline/runner.py`. Retain adapters temporarily for tests, then remove
  direct production callers.
- [ ] **P1.7 (M, depends P1.6):** Make `PipelinePlan` validate unique producers,
  dependencies, cycles, model-role ordering, checkpoint policy, and terminal vs
  item failure policy before loading models.
- [ ] **P1.8 (M, depends P1.1):** Normalize public error records and JSONL event
  envelopes to the contracts in `api.md`; add monotonic sequence numbers.
- [ ] **P1.9 (M, depends P1.2):** Rewrite configuration parsing to reject unknown
  keys, invalid ranges, unresolved relative paths, and unsupported mode fields.
- [ ] **P1.10 (S, depends P1.6):** Make CLI, overnight runner, dry run, and tests
  call the application service only.
- [ ] **P1.11 (M, depends P1.1-P1.10):** Delete obsolete duplicate key maps,
  legacy context accessors, and production `execute_parallel` assembly paths.
- [ ] **P1.12 (M, depends P1.11):** Generate pipeline documentation tables from
  the plan and CLI help snapshots from the parser.

## Integrated `src/worldgen` rewrite work

Phase 1 absorbs worldgen rewrite WP0 and WP1.

- [ ] **P1.WG1 (S, no dependencies):** Characterize the current `src/worldgen`
  outputs for several small seeds and add regression cases for drainage sinks,
  skipped region cells, shared-RNG coupling, duplicated colonist population, and
  stale expansion naming.
- [ ] **P1.WG2 (S, depends P1.WG1):** Inventory every caller of
  `WorldSnapshot`, `generate_world`, adapter helpers, and the prototype schema;
  mark the old API deprecated and forbid new imports.
- [ ] **P1.WG3 (M, depends P1.3):** Implement the normative fixed-point numeric
  profile, checked arithmetic, SHA-256 seed plan, SplitMix64, and stable IDs under
  `src/worldgen/` with golden vectors.
- [ ] **P1.WG4 (M, depends P1.2,P1.WG3):** Implement strict `WorldSpec` with the
  complete worldgen-1 fields, defaults, ranges, and resource preflight.
- [ ] **P1.WG5 (L, depends P1.4,P1.WG4):** Implement canonical JSON/grid chunks,
  world artifact envelopes, dependency DAG, atomic repository, and `WG-*` errors.
- [ ] **P1.WG6 (L, depends P1.6,P1.WG5):** Add the world-stage protocol,
  declarative worldgen plan, cancellation/events, bounded retry, checkpointing,
  and dependency-closure invalidation.
- [ ] **P1.WG7 (M, depends P1.WG3-P1.WG6):** Port the embedded miniature
  generator as a conformance test and make `worldgen conformance reference`
  reproduce its frozen byte length, site IDs, event count, and SHA-256.

Worldgen Phase 1 tests cover numeric overflow/rounding, RNG/seed/ID vectors,
unknown configuration, canonical encoding, atomic crash windows, dependency
cycles/hashes, synthetic worker independence, and the reference conformance vector.

## Target code example

```python
# src/domain/run_spec.py
from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class RunSpec:
    seed: int
    title: str
    tone: str = "mature_dark_fantasy"
    width: int = 1024
    height: int = 1024
    metres_per_world_cell: int = 8_000
    continent_count: int = 1
    history_years: int = 500
    civilization_count: int = 8

    def derive_seed(self, domain: str, item: str = "") -> int:
        raw = f"storyteller:v2:{self.seed}:{domain}:{item}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
```

```python
# src/pipeline/context.py
@dataclass
class RunContext:
    run_id: str
    spec: RunSpec
    artifacts: ArtifactRepository
    checkpoints: CheckpointRepository
    events: EventSink
    cancellation: CancellationToken
```

## File operations

Add `src/domain/`, `src/pipeline/context.py`, `src/pipeline/runner.py`, and focused
tests. Rewrite application/config/plan boundaries. Remove `world_mode`, generic
generation state, duplicated production runners, and deprecated `MAX_RETRIES`.
Do not delete v1 schemas, fixtures, packager, or mobile parsers yet.

## Focused tests

- RunSpec validation and serialization
- Seed golden vectors and domain separation
- Typed repository round trips
- Plan invalid dependency/cycle/resource cases
- Exact retry semantics and terminal error behavior
- Event sequence/schema stability
- Cancellation propagation
- All entry points use one application service
- Unknown configuration keys fail

## Required commands at phase exit

These commands must exist and pass by the end of this phase:

```bash
.venv/bin/mypy src scripts tests
.venv/bin/pytest -q tests/test_run_spec.py tests/test_seed_plan.py
.venv/bin/pytest -q tests/test_pipeline_runner.py tests/test_pipeline_plan_v2.py
.venv/bin/pytest -q tests/test_event_contract.py tests/test_config_v2.py
.venv/bin/python -m src.cli --help
```

## Exit checklist

- [ ] One typed run specification reaches every step.
- [ ] One runner owns production execution.
- [ ] Every artifact boundary returns an `ArtifactRef`.
- [ ] Seed derivation has versioned golden vectors.
- [ ] Retry, terminal failure, cancellation, and events are locked by tests.
- [ ] No production code reads title/tone/world settings from generic state.
- [ ] v1 remains only as a temporary downstream compatibility island.

## Phase 2 handoff

Phase 2 receives a stable `RunSpec`, seed plan, runner, artifact repository, and
step contract. It may replace `src/worldgen/` without changing application or
execution APIs.
