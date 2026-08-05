# Rewrite Phase 3: Civilizations and Full Historical Simulation

## Mission

Replace the simple population/history loop with a deterministic simulation that
creates sites, civilizations, economy, migration, diplomacy, wars, territorial
change, and a complete causal event ledger through a configurable present year.
Retain final state, every material event, and snapshots at year 0, every ten
years, and the final year.

## Entry state audit

| Current area | Disposition | Gap |
|---|---|---|
| `src/worldgen/civilizations.py` | Replace | Race/government placement and simple growth are not a full simulation |
| `Civilization`, `Site`, `HistoryEvent` in `models.py` | Replace | IDs/references/event causes/consequences/snapshots are insufficient |
| `adapter.py` history summary | Remove from authoritative layer | It truncates history for a prompt and loses causal structure |
| `world_snapshot.schema.json` history array | Prototype only | Final domains remain separate until Phase 6 freeze |

## Simulation boundary

Physical artifacts are read-only. Simulation owns sites, organizations,
populations, economies, diplomacy, territory, and events. It advances in
deterministic ticks, emits ordered events, and stops at `present_year`.

## Action plan

- [ ] **P3.1 (M, depends Phase 2):** Define immutable IDs and state models for
  sites, settlements, civilizations, populations, economy, diplomacy, and
  territory.
- [ ] **P3.2 (M, depends P3.1):** Implement deterministic site suitability and
  founding constrained by water, biome, resources, routes, and land capacity.
- [ ] **P3.3 (L, depends P3.2):** Implement civilization formation with culture,
  government, capabilities, needs, capital, and stable identity.
- [ ] **P3.4 (XL, depends P3.3):** Add population cohorts, births/deaths,
  migration, settlement growth/decline, and resource carrying capacity.
- [ ] **P3.5 (XL, depends P3.3,P3.4):** Add production, consumption, scarcity,
  trade, route use, and economic relationships.
- [ ] **P3.6 (XL, depends P3.3-P3.5):** Add diplomacy, alliance, rivalry, war,
  peace, conquest, collapse, and territory transitions.
- [ ] **P3.7 (L, depends P3.1):** Define a closed event type registry and causal
  consequence operations; every material state transition emits an event.
- [ ] **P3.8 (XL, depends P3.2-P3.7):** Implement a deterministic year/tick
  scheduler whose tie-breaking never depends on set/dict iteration.
- [ ] **P3.9 (M, depends P3.8):** Persist the complete ordered ledger and snapshots
  at year 0, every ten years, and the final year; deduplicate the final snapshot
  when it is already a ten-year boundary.
- [ ] **P3.10 (L, depends P3.9):** Add replay validation: reconstruct selected
  state from an earlier snapshot plus events and compare hashes.
- [ ] **P3.11 (M, depends P3.9):** Emit separate sites, civilizations, history,
  and snapshots artifact references with dependencies on Phase 2 domains.
- [ ] **P3.12 (M, depends P3.1-P3.11):** Replace old civilization generator and
  prompt-truncated history path; keep a read-only summary projection for Phase 4.

## Integrated `src/worldgen` rewrite work

Phase 3 absorbs worldgen rewrite WP5 and WP6.

- [ ] **P3.WG1 (M, depends Phase 2):** Add and hash builtin people, government,
  material, recipe, species, and supernatural registries; reject duplicate,
  unbalanced, or incompatible entries.
- [ ] **P3.WG2 (L, depends P3.WG1):** Generate languages, morphemes, names,
  scripts, flags, and heraldry from entity-local streams with deterministic
  collision/rejection handling.
- [ ] **P3.WG3 (L, depends P3.WG1):** Generate objective magic laws, belief
  claims, religions, institutions, taboos, cults, holy sites, costs, limits, and
  prohibited effects. Magic never bypasses physical/history validation.
- [ ] **P3.WG4 (L, depends P3.WG1-P3.WG3):** Replace race-conditioned culture
  tables with environmental/historical cultures and create conserved initial
  cohorts, stockpiles, governments, technologies, relationships, and territory.
- [ ] **P3.WG5 (XL, depends P3.1-P3.5,P3.WG4):** Simulate twelve monthly ticks
  per year for cohorts, disease, harvest, production, spoilage, consumption,
  resource depletion, trade, pricing, migration, and settlement capacity.
- [ ] **P3.WG6 (XL, depends P3.WG5):** Add deterministic proposals for
  construction, exploration, technology, reform, schism, succession, diplomacy,
  supplied war, occupation, peace, collapse, and recovery.
- [ ] **P3.WG7 (L, depends P3.WG5,P3.WG6):** Route every change through one
  exactly-once event applier and conserve cohorts, migrants, armies, goods,
  currency, deposits, and territory.
- [ ] **P3.WG8 (L, depends P3.WG7):** Commit monthly ledger batches and periodic
  snapshots atomically; verify prefix hashes and byte-identical genesis/snapshot
  replay.

Phase 3 cannot exit on a prose history list. The complete typed state, causal
ledger, snapshots, registry hashes, and conservation reports are mandatory.

## Target event example

```python
@dataclass(frozen=True)
class HistoryEvent:
    event_id: str
    year: int
    sequence: int
    kind: EventKind
    causes: tuple[str, ...]
    participants: tuple[str, ...]
    locations: tuple[str, ...]
    consequences: tuple[Consequence, ...]
    summary: str


def ordered_events(events: Iterable[HistoryEvent]) -> tuple[HistoryEvent, ...]:
    return tuple(sorted(events, key=lambda e: (e.year, e.sequence, e.event_id)))
```

Deterministic scheduler pattern:

```python
for year in range(1, spec.history_years + 1):
    intents = collect_intents(state, seeds.for_year(year))
    for intent in sorted(intents, key=lambda i: i.stable_sort_key):
        state, emitted = apply_intent(state, intent)
        ledger.extend(emitted)
```

## File operations

Add `src/worldgen/simulation/` modules for state, sites, population, economy,
diplomacy, conflict, events, scheduler, snapshots, and replay. Replace
`civilizations.py` production logic and old history models. Add simulation
fixtures under `tests/worldgen/`.

## Focused tests

- Site suitability and containment
- Carrying capacity and population conservation invariants
- Trade route and resource constraints
- Diplomacy/war transition state machines
- Territory remains valid and non-overlapping where required
- Causes reference earlier events
- Every consequence is applied exactly once
- Ledger ordering independent of collection iteration
- Snapshot replay equals recorded state
- Same physical world/history spec yields identical bytes
- Full ledger retained when narrative summary omits events

## Required commands at phase exit

```bash
.venv/bin/pytest -q tests/worldgen/simulation
.venv/bin/pytest -q -m history_property
.venv/bin/python -m src.cli simulate-world \
  --world tmp/world-phase2 --history-years 500 --output tmp/world-phase3
.venv/bin/python -m src.cli validate-world tmp/world-phase3
```

## Exit checklist

- [ ] Simulation reaches the configured present year deterministically.
- [ ] Final state, complete ledger, and year-0/ten-year/final snapshots are stored.
- [ ] Events contain causes, participants, locations, and consequences.
- [ ] Replay validation proves snapshot/ledger consistency.
- [ ] Physical facts remain byte-identical to Phase 2 inputs.
- [ ] Summary projections never replace full stored data.

## Phase 4 handoff

Phase 4 receives all physical and historical artifacts plus efficient projections
for prompting. It must enrich them without mutation and prove reconciliation.
