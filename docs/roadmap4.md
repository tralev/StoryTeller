# Rewrite Phase 4: World Bible Integration and Reconciliation

## Mission

Rewrite World Builder so the authoritative procedural world and full simulated
past are its mandatory inputs. Add a deterministic reconciliation gate that
rejects contradictions without modifying world data. The Bible may add only
contained local entities and narrative interpretation.

## Entry state audit

| Current area | Disposition | Gap |
|---|---|---|
| `src/models/world_builder.py` | Rewrite | Procedural context is optional/mode-dependent and v1-shaped |
| `src/worldgen/adapter.py` | Replace with projections | Current text projection truncates history and uses loose prose constraints |
| `world_builder_v1.j2` / `world_builder_v2.j2` | Replace with versioned v2 prompt set | Prompt rules are not a reconciliation boundary |
| `src/validators/consistency.py` | Retain ideas, split | Narrative checks do not validate full geographic/historical authority |
| `src/validators/composite.py` | Generalize | Needs mandatory reconciliation status and typed issues |
| `bible.schema.json` | Keep v1 until Phase 6 | New Bible schema evolves during this phase |

## Target flow

```text
World artifacts -> bounded prompt projections -> Bible candidate
 -> schema validation -> deterministic reconciliation
 -> optional semantic critic -> retry Bible only -> accepted Bible
```

The world repository is read-only throughout this phase.

## Action plan

- [ ] **P4.1 (M, depends Phase 3):** Define `WorldView` query APIs that expose
  typed regions, routes, sites, civilizations, events, and present state without
  passing giant dictionaries through prompts.
- [ ] **P4.2 (L, depends P4.1):** Build deterministic bounded projections for
  geography, climate/weather, resources, routes, civilizations, and relevant
  history. Record source IDs for every projection row.
- [ ] **P4.3 (M, depends P4.2):** Define the pre-freeze v2 Bible model with
  `authoritative_refs` and containing IDs for all added local entities.
- [ ] **P4.4 (L, depends P4.2,P4.3):** Replace World Builder prompt/rendering so
  all major procedural entities are addressed and no mode can omit world input.
- [ ] **P4.5 (XL, depends P4.3):** Implement `WorldReconciler` checks for entity
  identity, containment, coordinates, climate, biome/resources, adjacency,
  routes, territory/government, chronology, event causality, and present year.
- [ ] **P4.6 (M, depends P4.5):** Add precise issue codes/JSON paths and convert
  them into deterministic retry feedback.
- [ ] **P4.7 (M, depends P4.5):** Retain optional LLM critique for semantic/tone
  quality, but prevent it from overriding deterministic failures.
- [ ] **P4.8 (L, depends P4.4-P4.7):** Rewrite `WorldBuilder` as a checkpointed
  candidate/reconcile loop; dependencies include all world artifact IDs.
- [ ] **P4.9 (M, depends P4.8):** Add local-entity rules permitting buildings,
  streets, caves, ruins, items, and minor characters only with valid containers.
- [ ] **P4.10 (M, depends P4.8):** Produce a durable reconciliation report that
  records checked artifact IDs, ruleset version, issues, and accepted status.
- [ ] **P4.11 (S, depends P4.8):** Delete `world_mode` branches and any path that
  builds a Bible without procedural inputs.
- [ ] **P4.12 (M, depends P4.1-P4.11):** Rewrite Art Director input to use world
  maps, climate palettes, cultures, and accepted Bible references.

## Integrated `src/worldgen` rewrite work

Phase 4 owns the projection portion of worldgen rewrite WP8.

- [ ] **P4.WG1 (M, depends Phase 3):** Build typed world queries over every
  physical, ecological, cultural, magical, economic, person, and history artifact;
  do not materialize a lossy replacement snapshot.
- [ ] **P4.WG2 (L, depends P4.WG1):** Implement deterministic source-coverage
  projections and token-budget chunks whose records retain fact and source IDs.
- [ ] **P4.WG3 (M, depends P4.WG2):** Replace `src/worldgen/adapter.py` direct
  prose context with typed projection records; keep any legacy adapter isolated and
  read-only until Phase 6.
- [ ] **P4.WG4 (L, depends P4.WG2,P4.5):** Reconcile Bible geography, routes,
  climate, resources, ownership, government, persons, event chronology, objective
  magic, and belief epistemic status against authoritative facts.
- [ ] **P4.WG5 (M, depends P4.WG4):** Prove every retry changes only the Bible
  candidate; all procedural artifact bytes and dependency hashes remain unchanged.

Focused evidence adds complete projection source coverage, deterministic chunking,
magic/belief reconciliation, and immutable world hashes across every critic/retry
path.

## Target code example

```python
class WorldReconciler:
    def reconcile(self, world: WorldView, bible: BibleV2) -> ReconciliationReport:
        issues: list[ValidationIssue] = []
        issues += check_major_entities(world, bible)
        issues += check_containment(world, bible)
        issues += check_geography_and_routes(world, bible)
        issues += check_climate_resources(world, bible)
        issues += check_civilizations(world, bible)
        issues += check_chronology(world, bible)
        return ReconciliationReport(
            accepted=not any(i.severity == "error" for i in issues),
            world_artifact_ids=world.artifact_ids,
            ruleset_version=1,
            issues=tuple(issues),
        )
```

Local entity example:

```json
{
  "entity_id": "ruin_00000000000000000000000000000042",
  "kind": "ruin",
  "name": "The Bone Observatory",
  "contained_by": "region_00000000000000000000000000000012",
  "authoritative_refs": ["region_00000000000000000000000000000012", "event_00000000000000000000000000000341"]
}
```

## File operations

Add `src/world/` query/projection modules and
`src/validators/world_reconciler.py`. Rewrite World Builder, consistency/composite
composition, prompts, Bible boundary models, and Art Director inputs. Remove all
generation-mode branching. Keep v1 schemas/fixtures until Phase 6.

## Focused tests

- Projection determinism, source coverage, and token budget
- Valid enrichment of local contained entities
- Unknown region/civilization rejection
- Impossible route and climate/resource contradiction
- Territory/government mismatch
- Event cause/year/present-year contradictions
- World bytes unchanged by every retry
- Optional critic unavailable/failed status handling
- Reconciliation report dependency hashes

## Required commands at phase exit

```bash
.venv/bin/pytest -q tests/world/test_views.py tests/world/test_projections.py
.venv/bin/pytest -q tests/test_world_reconciler.py
.venv/bin/pytest -q tests/test_world_builder_v2.py tests/test_art_director_v2.py
.venv/bin/python -m src.cli generate-bible \
  --world tmp/world-phase3 --title "The Ashen Continent" --output tmp/world-phase4
.venv/bin/python -m src.cli reconcile-world \
  --world tmp/world-phase3 --bible tmp/world-phase4/bible.json
```

## Exit checklist

- [ ] No Bible can be produced without a complete procedural world.
- [ ] Deterministic reconciliation is mandatory and precise.
- [ ] Bible retries never mutate world artifacts.
- [ ] Local additions always name valid containers.
- [ ] Reconciliation report is durable and dependency-addressed.
- [ ] Art direction derives from world plus accepted Bible.

## Phase 5 handoff

Phase 5 receives immutable world artifacts, an accepted Bible, reconciliation
report, and style Bible. Narrative and media must preserve these references.
