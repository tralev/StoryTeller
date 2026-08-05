# `src/worldgen` Rewrite Plan

> Historical implementation decomposition. Work packages 0–8 have been absorbed
> into the current source and contract set; their unchecked boxes are retained as
> rationale and are not delivery status. `roadmap.md` is the sole active plan,
> including P9.WG1 legacy removal and subsequent hardening/evidence.

## Outcome

Replace the current prototype with a deterministic, validated, artifact-oriented
macro-to-micro generator implementing the `worldgen-1` specification. The rewrite
must generate the complete authoritative world before World Bible or narrative
generation. No narrative-only fallback or optional procedural mode remains.

This is a replacement plan. Temporary breakage is acceptable inside a phase, but
each phase ends with a working command, passing focused tests, and committed
canonical artifacts.

## Current implementation assessment

### Retain temporarily

- The public `generate_world(...)` name as a compatibility façade until callers
  migrate to `GenerateWorld`.
- `ProceduralWorldStep` only as a bridge to the existing pipeline service.
- Existing tests as characterization tests until their replacement phase lands.
- The current adapter only until typed World Bible projection replaces prompt-text
  assembly.

### Replace

| Current component | Problem | Replacement |
|---|---|---|
| `WorldRNG` | One mutable LCG stream; floats; choices depend on call order | SHA-256 domain seeds plus versioned SplitMix64 streams |
| `GridCell` | Mutable float container mixing unrelated domains | Immutable typed domain records and fixed-point chunk arrays |
| `WorldSnapshot` | Lossy summary; cannot retain full physical/history data | Artifact inventory plus typed `GeneratedWorld` index |
| `generate_terrain` | Layered value noise and quantile sea level only | Plates, continental mask, uplift, erosion, exact continent validation |
| `generate_climate` | Mutates grid; single west-east pass; drainage can terminate in sinks | Four-season climate relaxation plus priority-flood hydrology |
| `classify_biomes` | Overwrites classifications; ignores soil/geology/ecology | Total ordered biome table over validated physical inputs |
| `segment_regions` | Same-biome flood fill; skips tiny clusters and leaves cells unowned | Watershed/barrier multi-source Dijkstra with deterministic merge/split |
| `generate_civilizations` | Race stereotypes, shared RNG, free expansion/population, prose events | Data-driven peoples/cultures, conserved cohorts/economy, causal event ledger |
| `snapshot_to_bible_context` | Lossy text conversion is the integration contract | Typed fact projection and reconciliation inputs |
| `world_snapshot.schema.json` | v1 summary only | Per-domain schemas plus artifact envelopes and full inventory |

### Defects to prevent during migration

- Current canonical output contains floats and rounded presentation values.
- Adding an RNG call in terrain can change civilization history.
- River flow can stop at local depressions and has no basin/lake representation.
- Region segmentation may skip small land clusters without assigning them.
- Settlement expansion can duplicate population instead of transferring colonists.
- History lacks IDs, causes, ticks, before/after state, and replay.
- Expanded-site naming reads a stale outer-loop `race` variable.
- Regions and civilizations are mutated after construction.
- Pipeline configuration comes from `dict[str, Any]` keys rather than `WorldSpec`.
- Stable IDs are sequential display-oriented IDs and change when enumeration changes.

### Current file disposition

| Current file | Action |
|---|---|
| `src/worldgen/__init__.py` | Rewrite exports around `GenerateWorld`, `WorldSpec`, and `GeneratedWorld`. |
| `src/worldgen/models.py` | Delete after splitting typed records into domain modules; replace `WorldRNG`, floats, and mutable containers. |
| `src/worldgen/terrain.py` | Replace with plate, continent, terrain, erosion, and geology stages. |
| `src/worldgen/climate.py` | Replace with independent hydrology and four-season climate stages. |
| `src/worldgen/biomes.py` | Replace with soil, total biome table, resource, and ecology stages. |
| `src/worldgen/regions.py` | Replace with multi-source region segmentation, routes, geometry, maps, and indexes. |
| `src/worldgen/civilizations.py` | Replace with registry-driven society, economy, and causal history packages. |
| `src/worldgen/generator.py` | Keep façade temporarily; replace orchestration with application service, plan, and runner. |
| `src/worldgen/adapter.py` | Replace with typed story projection; remove direct prompt-text integration. |
| `src/worldgen/step.py` | Move to `adapters/pipeline_step.py`, then reduce it to application-service delegation. |
| `schemas/world_snapshot.schema.json` | Retain only as a legacy rejection/compatibility fixture until full domain schemas freeze, then delete. |

## Target package layout

```text
src/worldgen/
  __init__.py
  api.py                    GenerateWorld, GeneratedWorld, public queries
  spec.py                   WorldSpec and strict validation
  errors.py                 WG-* diagnostics
  numeric.py                fixed-point units, checked arithmetic, rounding
  rng.py                    SHA-256 seed plan and SplitMix64
  ids.py                    stable entity/artifact IDs
  canonical.py              canonical JSON and chunk encoding
  artifacts.py              envelopes, dependency graph, domain repository
  plan.py                   declarative generation DAG
  runner.py                 stage execution, cancellation, events, resume
  validation.py             validator protocol and composed acceptance
  registries/
    models.py               typed registry entries
    builtin.py              worldgen-1 people/government/material/recipe/magic data
    validate.py             registry validation and hashing
  physical/
    plates.py
    continents.py
    terrain.py
    erosion.py
    geology.py
    priority_flood.py
    hydrology.py
    climate.py
    soil.py
    biomes.py
    resources.py
    ecology.py
  spatial/
    regions.py
    routes.py
    geometry.py
    maps.py
    indexes.py
  society/
    languages.py
    names.py
    magic.py
    cultures.py
    religions.py
    governments.py
    sites.py
    civilizations.py
    cohorts.py
    economy.py
  history/
    state.py
    proposals.py
    events.py
    simulation.py
    replay.py
    snapshots.py
  local/
    models.py
    strata.py
    caves.py
    liquids.py
    heat.py
    support.py
    buildings.py
    generator.py
  story/
    opportunities.py
    projection.py
  adapters/
    pipeline_step.py         temporary application boundary
    legacy_snapshot.py       temporary read-only compatibility, then delete
```

Tests mirror this structure under `tests/worldgen/`; shared golden fixtures live
under `tests/fixtures/worldgen/`.

## Core target contracts

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar, Generic

T = TypeVar("T")

@dataclass(frozen=True)
class DomainArtifact(Generic[T]):
    artifact_id: str
    kind: str
    schema_version: str
    algorithm_profile: str
    dependency_ids: tuple[str, ...]
    dependency_hashes: tuple[tuple[str, str], ...]
    content_sha256: str
    value: T

@dataclass(frozen=True)
class GeneratedWorld:
    world_id: str
    spec_artifact_id: str
    artifact_ids: tuple[str, ...]
    validation_report_id: str
    spatial_index_id: str
    reference_index_id: str

class WorldStage(Protocol[T]):
    name: str
    algorithm_version: str
    dependencies: tuple[str, ...]

    def generate(self, context: "WorldgenContext") -> T: ...
    def validate(self, value: T, context: "WorldgenContext") -> tuple["Issue", ...]: ...

class WorldRepository(Protocol):
    def put(self, artifact: DomainArtifact[object]) -> None: ...
    def get(self, artifact_id: str) -> DomainArtifact[object]: ...
    def verify(self, artifact_id: str) -> bool: ...
    def publish_world(self, world: GeneratedWorld) -> Path: ...
```

The application service receives one frozen `WorldSpec`; stages never read
arbitrary pipeline state.

```python
class GenerateWorld:
    def execute(self, spec: WorldSpec, *, resume_run_id: str | None = None) -> GeneratedWorld:
        spec.validate()
        plan = build_worldgen_plan(spec)
        return WorldgenRunner(plan, repository, validators, events).run(spec, resume_run_id)
```

## Work package 0: Freeze and characterize the prototype

- [ ] Record current test result and golden outputs for several small seeds.
- [ ] Add regression tests demonstrating current defects: drainage sink, skipped
  region cells, shared-RNG coupling, population duplication, stale expansion name.
- [ ] Inventory every caller of `WorldSnapshot`, `generate_world`, adapter helpers,
  and `world_snapshot.schema.json`.
- [ ] Mark all current public worldgen types deprecated and prevent new imports.
- [ ] Add an architecture test forbidding new dependencies on legacy modules.
- [ ] Preserve prototype fixtures only as comparison inputs, not target goldens.

Exit gate: baseline behavior and all migration consumers are known.

## Work package 1: Deterministic kernel and contracts

- [ ] Implement fixed-point units and checked integer arithmetic.
- [ ] Implement SHA-256 domain seed derivation and SplitMix64 exactly.
- [ ] Add seed golden vectors for Python and future native readers/tools.
- [ ] Implement strict `WorldSpec`, including all defaults/ranges and resource
  preflight.
- [ ] Implement stable IDs independent of names and enumeration order.
- [ ] Implement canonical JSON and canonical integer-grid chunks.
- [ ] Implement artifact envelopes, dependency DAG, hashes, repository, and atomic
  commit.
- [ ] Implement `WG-*` typed errors and validator result models.
- [ ] Implement the declarative stage plan and dependency-closure invalidation.
- [ ] Port the embedded miniature generator into a conformance test and require its
  published hash.

Tests:

- numeric boundaries/overflow and rounding;
- SplitMix64/seed/ID vectors;
- configuration minimum/maximum/unknown fields;
- canonical encoding and Unicode normalization;
- atomic write crash windows;
- dependency cycle/broken hash/invalidation;
- worker/order independence of a synthetic stage plan.

Exit gate: `worldgen conformance reference` prints the specified miniature hash and
all later stages can commit typed artifacts.

## Work package 2: Physical world

- [ ] Implement spaced plate centers, Voronoi assignment, plate motion, and boundary
  classification.
- [ ] Implement continental masks and exact configurable continent count.
- [ ] Implement uplift/rift/transform relief and fixed-point fractal texture.
- [ ] Implement synchronous thermal and hydraulic erosion with mass ledger.
- [ ] Implement geological strata, faults, volcanic areas, soil parent material.
- [ ] Implement priority flood, deterministic flow direction, accumulation,
  watersheds, lakes, outlets, rivers, tributaries, aquifers, salinity, glaciers.
- [ ] Implement four-season solar temperature, winds, moisture relaxation,
  orographic rain, snow, and hazard probabilities.

Tests:

- requested one and multiple continent cases;
- plate coverage/boundary symmetry;
- erosion conservation;
- hand-calculated priority-flood and flow fixtures;
- river termination, basin and tributary invariants;
- climate range, lapse, coastal moderation, rain shadows;
- deterministic bytes across workers and supported platforms.

Exit gate: complete physical artifacts validate without biome or narrative code.

## Work package 3: Soils, biomes, resources, and ecology

- [ ] Implement soil depth, fertility, drainage, erosion/deposition classes.
- [ ] Implement the total ordered biome decision table without override mutation.
- [ ] Implement deposit geometry, depth, grade, quantity, and geology compatibility.
- [ ] Implement renewable resource yields and depletion.
- [ ] Implement habitats, species, food-web bounds, migration corridors,
  domestication, extinction, net productivity, and carrying capacity.
- [ ] Create and hash the builtin material/species/recipe registries.

Tests:

- every cell classified exactly once;
- all boundary rows in the biome table;
- invalid geology/resource and ecology/biome pairs;
- predator/prey energy and renewable-yield bounds;
- deposit conservation and deterministic discovery state;
- registry unknown/duplicate/inconsistent entry rejection.

Exit gate: every land and water cell has valid physical/ecological context.

## Work package 4: Regions, routes, maps, and indexes

- [ ] Replace biome flood fill with deterministic multi-source Dijkstra using
  watersheds, barriers, travel cost, and connectivity.
- [ ] Implement deterministic split/merge and symmetric adjacency.
- [ ] Implement seasonal route A* for roads, trails, rivers, sea lanes, passes, and
  later constructed tunnels.
- [ ] Implement route capacity and traversability.
- [ ] Emit canonical geometry and scalar map layers.
- [ ] Implement deterministic raster rendering and label placement.
- [ ] Build spatial and reference indexes and prove rebuild equality.

Tests:

- complete cell ownership, no skipped small clusters;
- connected regions and symmetric shared boundaries;
- route endpoint/geometry/cost/capacity fixtures;
- unreachable routes rejected;
- map feature source coverage and raster determinism;
- incoming/outgoing reference and spatial-index completeness.

Exit gate: any entity/cell can be queried spatially and feasible travel is known.

## Work package 5: Peoples, cultures, magic, and initial civilizations

- [ ] Implement the versioned builtin registry from the specification.
- [ ] Replace race-conditioned governments/cultures with environmental and
  historical archetypes.
- [ ] Generate languages, morphemes, names, scripts, flags, and heraldry from
  entity-local streams.
- [ ] Generate objective magic laws, belief claims, religions, institutions,
  taboos, cults, and holy sites with hard cost/prohibition validation.
- [ ] Score initial sites from water, ecology, defense, routes, resources, hazards,
  and crowding.
- [ ] Create capitals, cohorts, stockpiles, governments, initial territory,
  technologies, and relationships without free resources or population.

Tests:

- naming grammar vectors and collision/rejection behavior;
- government/succession constraints;
- true/false/uncertain belief separation;
- magic prerequisites, costs, prohibitions, and no validator bypass;
- settlement suitability/separation/containment;
- initial cohort, stockpile, ownership, and territory conservation.

Exit gate: valid initial simulation state exists at history year zero.

## Work package 6: Economy and causal history

- [ ] Implement monthly cohorts, births, deaths, migration, disease, harvest,
  production, spoilage, consumption, stockpiles, trade, prices, and depletion.
- [ ] Implement yearly construction, exploration, technology, religion, diplomacy,
  reform, succession, war, occupation, peace, collapse, and recovery proposals.
- [ ] Collect proposals first, then resolve in stable order.
- [ ] Emit events with IDs, causes, participants, locations, before/after changes,
  tags, and provenance.
- [ ] Apply every state change exactly once through one event applier.
- [ ] Commit monthly event batches and periodic snapshots atomically.
- [ ] Implement genesis/snapshot replay and prefix hashes.
- [ ] Retain the complete ledger even when no narrative references it.

Tests:

- population/migrant/army/goods/currency/deposit conservation;
- recipe and route-capacity accounting;
- disease compartment and travel propagation;
- legal/disputed succession and interregnum;
- motivated, supplied war and explicit peace/territory events;
- cause ordering, dead participant rejection, exactly-once change application;
- replay from genesis and every snapshot;
- history worker/order and resume equivalence.

Exit gate: 500 default years replay byte-identically and validate causally.

## Work package 7: Complete local 3D worlds

- [ ] Derive local boundary conditions from site/macro artifacts.
- [ ] Generate local surface, strata, deposits, caves, aquifers, rivers/coasts, and
  magma using site-specific streams.
- [ ] Generate roads, parcels, culturally coherent buildings, workshops,
  stockpiles, and event scars.
- [ ] Implement legal 3D movement edges and hierarchical A*.
- [ ] Implement bounded synchronous water/magma, heat, and structural support
  convergence for generation snapshots.
- [ ] Generate required local maps for every registered site and retain
  additional important maps.

Tests:

- macro geology/climate/route/ownership/history reconciliation;
- cave connectivity/sealed-state validity;
- fluid and heat conservation;
- stair/ramp and route path connectivity;
- deterministic collapse components;
- local retry and crash/resume equivalence.

Exit gate: all registered-site local maps add detail without changing macro facts.

## Work package 8: Story projection and pipeline integration

- [ ] Implement deterministic opportunity extraction over authoritative facts.
- [ ] Implement typed World Bible projection with coverage and token-budget chunks.
- [ ] Ensure projection is lossy but world artifacts are never discarded.
- [ ] Replace `snapshot_to_bible_context` with typed facts and source IDs.
- [ ] Add reconciliation inputs so Bible/narrative cannot contradict the world.
- [ ] Replace arbitrary `PipelineContext.state` keys with `WorldSpec`.
- [ ] Make `GenerateWorld` the only application entry point used by CLI and GUI.
- [ ] Checkpoint per domain/history batch/local map and resume through the
  application service.
- [ ] Update package inventory to retain every procedural artifact.

Tests:

- opportunity facts/references/routes and deterministic scoring;
- projection source coverage and bounded deterministic chunks;
- immutable world bytes across Bible retries;
- unknown or contradictory Bible entities rejected;
- CLI/GUI/service `WorldSpec` equality;
- interrupted/full-run equivalence and complete package inventory.

Exit gate: the production pipeline always runs worldgen before World Bible and
publishes full procedural data.

## Work package 9: Remove the prototype and harden

- [ ] Remove `GridCell`, `WorldSnapshot`, legacy enums, old RNG, old generator
  modules, prompt adapter, and `world_snapshot.schema.json`.
- [ ] Remove narrative/procedural/hybrid configuration and fallback branches.
- [ ] Convert surviving characterization tests to v1 rejection or delete them.
- [ ] Add property, mutation, fuzz, performance, memory, cancellation, and security
  suites.
- [ ] Benchmark named world sizes and record stage/chunk resource profiles.
- [ ] Verify Python/platform matrices and first-difference diagnostics.
- [ ] Run a complete real world through World Bible, narrative, assets, package,
  Android, and iOS acceptance.

Exit gate: no source import or schema reference points to the prototype; all
required procedural artifacts and tests pass release acceptance.

## Dependency and parallel-work plan

```text
WP0
 └─ WP1 deterministic kernel
     └─ WP2 physical world
         ├─ WP3 ecology/resources
         │   └─ WP5 societies ─► WP6 history ─► WP7 local maps
         └─ WP4 regions/routes ──┘                 │
                                                   ▼
                                            WP8 integration
                                                   ▼
                                            WP9 hardening
```

Within WP2, plates/terrain precede geology and hydrology; climate depends on both
terrain and hydrology. Within WP3, soil precedes biomes, then resources/ecology.
WP4 geometry and map-rendering work may proceed in parallel after physical schemas
stabilize. Registry/language work in WP5 may proceed alongside WP3–4, but site and
civilization placement waits for their outputs.

## Compatibility strategy

Do not make the new model implement the old `WorldSnapshot` schema. During WP1–8,
one isolated `legacy_snapshot.py` adapter may derive the old summary for still-
unmigrated tests and callers. It is read-only, carries no authoritative data, emits
a deprecation diagnostic, and is deleted in WP9.

New modules never import legacy models. An architecture test enforces that rule.
The old package continues passing until its consumer migrates; then its tests are
replaced, not expanded.

## Commands required at each work-package exit

```bash
.venv/bin/mypy src/worldgen tests/worldgen
.venv/bin/pytest -q tests/worldgen -m "not performance and not cross_platform"
.venv/bin/pytest -q tests/worldgen -m determinism
.venv/bin/python -m src.worldgen conformance reference
```

After WP6 add history replay/resume commands; after WP7 add local-map tests; after
WP8 add full pipeline/package acceptance; WP9 runs the complete release matrix.

## Completion criteria

- All required specification domains have immutable typed artifacts.
- Canonical procedural output contains no floats or process-dependent ordering.
- Default one-continent and configurable multi-continent worlds validate.
- Physical water/climate/ecology and spatial routes are coherent.
- Population, resources, armies, trade, disease, and history conserve state.
- Every event has causes and replayable changes.
- Local maps reconcile with macro facts.
- Complete procedural data is packaged even when unused by the story.
- Bible and narrative projection cannot mutate authoritative world state.
- Worker counts, supported platforms, output paths, and resume do not change bytes.
- The embedded reference conformance vector and all domain goldens pass.
- The old worldgen models, schema, adapter, modes, and fallback code are gone.
