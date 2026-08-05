# Rewrite Phase 2: Authoritative Physical World

## Mission

Replace the compact procedural prototype with a deterministic, retained physical
world: terrain, hydrology, climate, seasons/weather regimes, biomes, resources,
regions, routes, and derived world/region maps. The default is one configurable
continent. Narrative generation remains disabled during this phase.

## Entry state audit

| Current file | Disposition | Gap |
|---|---|---|
| `src/worldgen/models.py` | Replace | Mutable dataclasses and compact snapshot omit retained grids and domain provenance |
| `terrain.py` | Rewrite | Basic noise/sea threshold does not guarantee continent topology |
| `climate.py` | Split | Hydrology and climate are simplified and coupled |
| `biomes.py` | Rewrite tables/contracts | No resource ecology contract |
| `regions.py` | Rewrite | Region representation loses authoritative cell geometry |
| `generator.py` | Replace with domain pipeline | Returns only one compact object |
| `world_snapshot.schema.json` | Keep as prototype only | v2 schema freeze waits for Phase 6 |
| `tests/test_worldgen.py` | Split into domain/property tests | One broad file is insufficient for algorithm invariants |

## Target domains

```text
WorldIndex
TerrainGrid -> Hydrology -> Climate/Seasons -> Biomes -> Resources
            -> Regions/Adjacency -> Routes -> Derived Maps
```

Integer cell coordinates are canonical. `metres_per_world_cell` converts scale.
All structured domains, including grids, survive into the future package.

## Action plan

- [ ] **P2.1 (M, depends Phase 1):** Create immutable grid primitives,
  coordinate, dimensions, cell-index, and deterministic serialization types.
- [ ] **P2.2 (L, depends P2.1):** Implement versioned terrain generation with
  elevation, ocean/land, slope, and deterministic continent labeling.
- [ ] **P2.3 (XL, depends P2.2):** Add `hydrology.py`: flow directions,
  watersheds, sinks/lakes, rivers, discharge, coastlines, and invariants.
- [ ] **P2.4 (XL, depends P2.2,P2.3):** Add `weather.py` and rewrite climate for
  temperature, precipitation, wind, season profiles, and weather regimes.
- [ ] **P2.5 (L, depends P2.4):** Rewrite biome classification as a versioned
  ruleset with complete land-cell coverage.
- [ ] **P2.6 (L, depends P2.2-P2.5):** Add deterministic geology/natural resource
  occurrence compatible with terrain and biome rules.
- [ ] **P2.7 (XL, depends P2.5):** Rewrite regions to retain cell membership,
  stable IDs, center/area, boundary geometry, and symmetric adjacency.
- [ ] **P2.8 (L, depends P2.3,P2.6,P2.7):** Generate traversable route graph
  candidates with distance, terrain cost, river crossing, and seasonal risk.
- [ ] **P2.9 (L, depends P2.7,P2.8):** Add deterministic renderer for a world map
  and one map per region. Maps are derived, not authoritative.
- [ ] **P2.10 (M, depends P2.1-P2.9):** Emit separate artifact references for
  world index, terrain, hydrology, climate, biomes, resources, regions, routes,
  and maps.
- [ ] **P2.11 (M, depends P2.10):** Add algorithm-version golden fixtures for
  small grids and property tests for larger randomized specifications.
- [ ] **P2.12 (S, depends P2.10):** Remove the old compact `WorldSnapshot` from
  production flow; retain a temporary adapter only for old tests until Phase 6.

## Integrated `src/worldgen` rewrite work

Phase 2 absorbs worldgen rewrite WP2, WP3, and WP4. In addition to P2.1–P2.12:

- [ ] **P2.WG1 (L, depends P2.1):** Add spaced plate centers, Voronoi ownership,
  motion vectors, and convergent/divergent/transform boundary artifacts.
- [ ] **P2.WG2 (XL, depends P2.WG1):** Enforce exact configurable continent
  count, minimum area, adjustment ledger, tectonic relief, and synchronous thermal
  and hydraulic erosion with mass conservation.
- [ ] **P2.WG3 (L, depends P2.WG2):** Generate geological strata, faults,
  volcanoes, parent material, deposit geometry/depth/grade/quantity.
- [ ] **P2.WG4 (XL, depends P2.WG2,P2.WG3):** Implement priority flood, flow
  direction/accumulation, watersheds, lakes/outlets, tributaries, seasonal rivers,
  aquifers, salinity, snow, and glaciers.
- [ ] **P2.WG5 (XL, depends P2.WG4):** Implement four-season integer solar
  temperature, wind bands, moisture relaxation, rain shadows, snow and hazards.
- [ ] **P2.WG6 (L, depends P2.WG3-P2.WG5):** Add soil, total ordered biome table,
  renewable yields, species, food webs, migration corridors, extinction, net
  productivity, and carrying capacity.
- [ ] **P2.WG7 (L, depends P2.WG6):** Replace same-biome flood fill with
  watershed/barrier multi-source Dijkstra and deterministic split/merge; every
  non-ocean cell belongs to exactly one region.
- [ ] **P2.WG8 (L, depends P2.WG7):** Implement stable A* route geometry,
  seasonal cost/capacity, canonical map features/rendering, and rebuildable spatial
  and reference indexes.
- [ ] **P2.WG9 (M, depends P2.WG1-P2.WG8):** Commit independent plates, terrain,
  geology, hydrology, climate, soil, biome, resource, species, ecology, region,
  route, map, and index artifacts; retain the legacy snapshot only through an
  isolated read-only adapter.

Additional exit evidence includes erosion mass balance, hand-calculated basin
fixtures, moisture conservation bounds, complete cell ownership, food-web energy
bounds, deposit conservation, route capacity, index rebuild equality, and worker/
platform canonical identity.

## Target code example

```python
@dataclass(frozen=True)
class GridSpec:
    width: int
    height: int
    metres_per_world_cell: int

    def index(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError((x, y))
        return y * self.width + x


@dataclass(frozen=True)
class Terrain:
    algorithm_version: int
    grid: GridSpec
    elevation: tuple[int, ...]       # normalized fixed-point values
    land: tuple[bool, ...]
    continent_id: tuple[int, ...]
```

Fixed-point integers are required for authoritative simulation values; floats are
limited to noncanonical preview/UI calculations.

Hydrology invariant example:

```python
def validate_river(edges: Sequence[RiverEdge], terrain: Terrain) -> None:
    for edge in edges:
        if edge.discharge <= 0:
            raise WorldInvariantError("RIVER_NON_POSITIVE_DISCHARGE")
        if edge.upstream == edge.downstream:
            raise WorldInvariantError("RIVER_SELF_LOOP")
```

## File operations

Add `src/worldgen/grid.py`, `hydrology.py`, `weather.py`, `resources.py`,
`routes.py`, `maps.py`, `validation.py`, and domain-specific tests. Rewrite
terrain/climate/biomes/regions/generator/models. Replace production use of
`WorldSnapshot`; do not delete the v1 schema yet.

## Focused tests

- Cross-platform seed golden vectors
- Requested default one-continent result and configurable continent counts
- Grid bounds/coverage and canonical serialization
- River continuity, lake/basin validity, coastline consistency
- Climate range and seasonal determinism
- Biome/resource compatibility
- Region connectivity/adjacency symmetry
- Route endpoint and traversability rules
- Map pixel determinism and label/geometry references
- Worker/order independence

## Required commands at phase exit

```bash
.venv/bin/pytest -q tests/worldgen/test_grid.py tests/worldgen/test_terrain.py
.venv/bin/pytest -q tests/worldgen/test_hydrology.py tests/worldgen/test_climate.py
.venv/bin/pytest -q tests/worldgen/test_biomes_resources.py
.venv/bin/pytest -q tests/worldgen/test_regions_routes.py tests/worldgen/test_maps.py
.venv/bin/pytest -q -m worldgen_property
.venv/bin/python -m src.cli generate-world --seed 42 --output tmp/world-phase2
```

`generate-world` is added in this phase as a diagnostic command and must emit all
physical artifacts plus maps without invoking an LLM.

## Exit checklist

- [ ] Physical domains cover every configured world cell.
- [ ] Default output has one continent and configurable scale.
- [ ] Hydrology, climate, biomes, resources, regions, and routes validate.
- [ ] World and region maps derive from authoritative data.
- [ ] Same spec produces identical bytes across supported Python platforms.
- [ ] All domain artifacts are independently hashed and checkpointable.

## Phase 3 handoff

Phase 3 receives immutable physical artifacts and route/resource constraints. It
may add sites, civilizations, economy, and history but cannot mutate Phase 2
facts.
