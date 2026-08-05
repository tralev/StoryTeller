# Procedural World Generation

## Document purpose

This document is a self-contained design and implementation guide for generating
a complete dark-fantasy world. It defines what can be generated, how generation
flows from planetary-scale facts to story-scale detail, which data must be retained,
how deterministic simulation works, and how to validate the result.

The generator creates an authoritative world before any prose is written. Later
narrative systems may select, summarize, and enrich that world, but they may not
rewrite its physical geography, climate, civilizations, or recorded history.

The intended default is one continent. The same design supports several continents
without creating a separate generation mode. All generated domains are retained in
the final world dataset even when a particular story does not use them.

## Design goals

The generator must produce a world that is:

- deterministic from a master seed, algorithm version, and explicit specification;
- physically coherent enough that rivers, climate, travel, settlement, and trade
  agree with one another;
- historically causal rather than a collection of unrelated flavor sentences;
- useful at both macro scale and local story scale;
- fully inspectable, serializable, and independently validatable;
- capable of adding small local entities without contradicting authoritative facts;
- independent of language models for canonical facts;
- stable under worker-count and iteration-order changes;
- rich enough to support maps, a World Bible, stories, images, music, and a local
  Game Master.

## Normative status and conformance

This document is the sole reference specification for procedural world generation.
The words **must**, **must not**, **required**, **shall**, and **shall not** are
normative. **Should** states the recommended implementation unless measured evidence
justifies a documented algorithm-version change. **May** denotes an optional output
that cannot change required facts when omitted.

An implementation conforms only when it:

1. accepts the complete `WorldSpec` defined here and rejects values outside its
   declared constraints;
2. produces every required domain in the declared dependency order;
3. uses the numeric, seed, identifier, ordering, and serialization rules here;
4. passes every domain invariant and cross-domain acceptance rule;
5. retains the complete authoritative procedural state and history ledger;
6. emits the required artifact envelope, provenance, indexes, and validation report;
7. matches golden vectors for its declared algorithm-profile version;
8. fails explicitly rather than selecting an undocumented fallback.

There are no narrative-only, procedural-only, or hybrid modes. The one pipeline is
procedural world followed by derived narrative use. Language-model output is never
an input to an authoritative procedural stage.

### `worldgen-1` algorithm profile

The first normative profile is `worldgen-1`. These values are defaults, not hidden
constants:

| Parameter | Default | Valid range/constraint |
|---|---:|---|
| world width | 1024 cells | 32–8192 |
| world height | 1024 cells | 32–8192 |
| continents | 1 | 1–16; each meets minimum land area |
| metres per world cell | 8,000 | integer, 250–100,000 |
| sea level | 380,000 ppm | 50,000–950,000 ppm |
| plate count | 24 | 4–256; not less than continents |
| erosion passes | 32 | 0–512 |
| climate seasons | 4 | exactly 4 in `worldgen-1` |
| climate relaxation passes | 64 | 8–512 |
| history duration | 500 years | 0–10,000 |
| history ticks per year | 12 | exactly 12 in `worldgen-1` |
| initial civilizations | 8 | 1–256 |
| local site width/height | 128 cells | 32–1024 each |
| local z-levels | 32 | 4–256 |
| local metres per cell | 2 | integer, 1–20 |
| snapshot interval | 10 years | exactly 10 in `worldgen-1` |

The generator does not impose a maximum final package size. It must perform a
preflight estimate for memory, working disk, and output disk and abort with a
resource diagnostic if the requested world cannot be generated safely.

### Required versus optional domains

Required domains are specification, seed plan, plates, terrain, geology,
hydrology, four-season climate, soils, biomes, resources, ecology, regions, travel,
peoples, cultures, religions, governments, civilizations, sites, economy, complete
history, maps, story opportunities, spatial/reference indexes, provenance, and
validation evidence.

Local 3D maps are required for every registered site, including sites unused by
the produced narrative. Named
individuals are required for all office holders and event participants; background
population may remain cohort-based. Decorative raster layers are derivable and may
be regenerated from canonical geometry.

## Canonical vocabulary

| Term | Exact meaning |
|---|---|
| fact | Immutable committed statement identified by stable ID and provenance |
| domain | One typed, independently hashed procedural output |
| cell | One coordinate in the continental surface grid |
| local tile | One `(x,y,z)` coordinate inside a registered site's local map |
| entity | Stable-ID object such as region, site, civilization, person, route, deposit, species, or event |
| cohort | Aggregated people sharing site, age band, culture, and health state |
| event | Immutable causal state transition with before/after values |
| snapshot | Complete replay checkpoint derived from the event ledger |
| opportunity | Non-authoritative story candidate referencing existing facts |
| enrichment | New minor local entity constrained by existing authoritative facts |
| canonical bytes | Deterministically encoded content used for identity and comparison |

Display names are mutable presentation fields only through explicit history events;
stable IDs never depend on names.

## What the world can contain

### Physical world

- continents, islands, coastlines, ocean basins, shelves, and sea regions;
- tectonic plates, boundaries, uplift zones, rifts, fault lines, and volcanoes;
- elevation, slope, aspect, roughness, soil depth, and underground strata;
- watersheds, drainage basins, rivers, tributaries, lakes, wetlands, aquifers,
  glaciers, and seasonal floodplains;
- latitude, prevailing winds, temperature, rainfall, rain shadows, humidity,
  drainage, seasonality, storms, droughts, and long-term climate bands;
- biomes, habitats, vegetation productivity, fertility, hazards, and carrying
  capacity;
- stone, ores, fuel, timber, fibers, food sources, medicinal plants, gems, salt,
  clay, and rare magical materials;
- regions, natural landmarks, mountain passes, navigable waters, and travel costs;
- a coarse surface map plus a sparse 3D local map for every registered site.

### Living world

- plant and animal species or archetypes, habitat ranges, migration, predation,
  domestication potential, rarity, and extinction;
- sapient peoples with environmental preferences and biological constraints;
- settlements, capitals, villages, forts, monasteries, mines, ports, ruins, roads,
  bridges, canals, farms, and workshops;
- civilizations, tribes, houses, guilds, cults, religions, languages, governments,
  laws, economies, technologies, armies, and diplomatic relations;
- named people, families, offices, skills, beliefs, needs, moods, relationships,
  possessions, injuries, deaths, and legacies;
- stockpiles, production recipes, resource flows, shortages, trade, prosperity,
  disease, famine, migration, and population change.

### Historical world

- foundations, successions, discoveries, constructions, reforms, schisms,
  expeditions, trade agreements, alliances, raids, wars, sieges, disasters,
  plagues, migrations, collapses, and cultural renaissances;
- explicit causes, participants, locations, state changes, and consequences;
- complete event ledger and periodic snapshots;
- surviving scars: abandoned roads, ruins, disputed borders, memorials, grudges,
  changed religions, lost techniques, refugee communities, and depleted deposits;
- unresolved pressures that can become story premises without inventing a new
  world contradiction.

### Story-facing derivations

- interesting frontiers, chokepoints, contested resources, dangerous routes, and
  culturally mixed settlements;
- mysteries with factual answers in history or geology;
- factions with goals, capacity, relationships, and credible constraints;
- candidate protagonists, antagonists, patrons, witnesses, and local specialists;
- locations suitable for narrative nodes and feasible routes between them;
- visual palettes derived from biome, season, culture, material, and time of day;
- musical descriptors derived from culture, instruments, danger, place, and mood;
- revealable facts indexed by the story nodes through which a player can learn them.

### Cosmology, religion, and magic

A mature dark-fantasy world also requires supernatural rules. These are generated
after physical laws and before cultures/history so that later events can depend on
them without allowing magic to become an unexplained exception.

- cosmological layers, afterlife claims, celestial cycles, and metaphysical places;
- gods, saints, spirits, demons, ancestors, and disputed/false entities;
- magical sources, costs, limits, transmission, corruption, detection, and
  countermeasures;
- holy sites, relics, taboos, cults, rites, schisms, heresies, and institutions;
- supernatural hazards and resources linked to exact places or historical events.

Every supernatural rule declares whether it is objectively true, culturally
believed, uncertain to inhabitants, or false. Objective magic has deterministic
mechanics:

```python
@dataclass(frozen=True)
class MagicLaw:
    id: str
    source: str
    prerequisites: tuple[str, ...]
    costs: tuple[tuple[str, int], ...]
    effects: tuple[str, ...]
    prohibited_effects: tuple[str, ...]
    range_cells: int
    reliability_ppm: int
    corruption_ppm: int

@dataclass(frozen=True)
class BeliefClaim:
    id: str
    culture_id: str
    subject_id: str
    claim: str
    epistemic_status: Literal["true", "false", "uncertain", "metaphorical"]
    evidence_fact_ids: tuple[str, ...]
```

Magic may transform a physical fact only through an explicit event whose law
permits the effect and pays its cost. A magical river reversal, floating fortress,
resurrection, or ageless ruler is valid only when the relevant law and historical
changes explain it. “Magic” is never a generic validator bypass.

### Languages and naming

Each language stores a phoneme inventory, syllable grammar, morphology, writing
system, and deterministic evolution rules. Names are assembled from semantic
morphemes and may change through sound shifts, conquest, translation, or religious
reform.

```python
@dataclass(frozen=True)
class Language:
    id: str
    consonants: tuple[str, ...]
    vowels: tuple[str, ...]
    syllable_patterns: tuple[str, ...]
    morphemes: tuple[tuple[str, str], ...]  # meaning, surface form
    writing_system: str

def generate_name(language: Language, meanings: tuple[str, ...], seed: int) -> str:
    lexicon = dict(language.morphemes)
    parts = [lexicon[m] for m in meanings if m in lexicon]
    if not parts:
        rng = SplitMix64(seed)
        pattern = language.syllable_patterns[rng.below(len(language.syllable_patterns))]
        parts = [realize_syllable(pattern, language, rng)]
    return "".join(parts).capitalize()

def realize_syllable(pattern: str, language: Language, rng: SplitMix64) -> str:
    output: list[str] = []
    for token in pattern:
        if token == "C":
            output.append(language.consonants[rng.below(len(language.consonants))])
        elif token == "V":
            output.append(language.vowels[rng.below(len(language.vowels))])
        else:
            output.append(token)
    return "".join(output)
```

`realize_syllable` replaces `C` and `V` tokens from the ordered consonant/vowel
inventories using the supplied RNG. Other characters are literal. Profanity,
duplicate, confusable, and reserved-name filters run deterministically; rejection
advances only that entity's name stream.

## Scale model

Generation uses a hierarchy rather than one enormous uniform grid:

```text
World
└── Continent (one by default, several configurable)
    ├── Region / drainage basin / political territory
    │   ├── Site: city, village, fort, ruin, shrine, mine
    │   │   ├── Local map: surface cells and sparse z-level chunks
    │   │   ├── Building / stockpile / workshop / route node
    │   │   └── Person / item / local event
    │   └── Route: road, river, sea lane, pass, tunnel
    └── History: events refer to stable entities at every level
```

The continental grid answers macro questions: climate, watersheds, biomes,
territory, settlement suitability, and long-distance travel. Every registered
site receives a sparse local 3D grid whose seed and boundary conditions derive
from the authoritative macro cell. Sparse chunks avoid a planet-sized dense voxel
array while retaining caves, mines, buildings, aquifers, magma, and local
pathfinding for narrative-used and unused sites alike.

Recommended coordinate representation:

```python
from dataclasses import dataclass

@dataclass(frozen=True, order=True)
class Cell:
    x: int
    y: int

@dataclass(frozen=True, order=True)
class LocalCell:
    site_id: str
    x: int
    y: int
    z: int

@dataclass(frozen=True)
class Scale:
    metres_per_world_cell: int
    millimetres_per_local_cell: int
    elevation_millimetres_per_level: int
```

Coordinates never rely on an unlabeled tuple. Every entity declares its coordinate
space and scale.

## Deterministic foundation

Never use global random state, Python's `hash()`, set iteration order, wall-clock
time, or worker completion order to make world decisions. Each domain and entity
receives a derived seed.

```python
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
import math
import unicodedata

MASK64 = (1 << 64) - 1

def derive_seed(master_seed: int, domain: str, *parts: object) -> int:
    payload = "\x1f".join([str(master_seed), domain, *(str(p) for p in parts)])
    digest = sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)

class SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & MASK64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def below(self, exclusive_upper: int) -> int:
        if exclusive_upper <= 0:
            raise ValueError("upper bound must be positive")
        limit = ((1 << 64) // exclusive_upper) * exclusive_upper
        while True:
            value = self.next_u64()
            if value < limit:
                return value % exclusive_upper

def rng_for(master_seed: int, domain: str, *parts: object) -> SplitMix64:
    return SplitMix64(derive_seed(master_seed, domain, *parts))

def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))

PPM = 1_000_000

def _fade_ppm(value_ppm: int) -> int:
    squared = value_ppm * value_ppm // PPM
    return squared * (3 * PPM - 2 * value_ppm) // PPM

def _lattice_ppm(seed: int, x: int, y: int) -> int:
    value = derive_seed(seed, "lattice", x, y)
    return value * (2 * PPM) // MASK64 - PPM

def noise2_ppm(x_ppm: int, y_ppm: int, seed: int) -> int:
    """Deterministic fixed-point value noise in [-PPM, PPM]."""
    x0, y0 = x_ppm // PPM, y_ppm // PPM
    x1, y1 = x0 + 1, y0 + 1
    tx = _fade_ppm(x_ppm - x0 * PPM)
    ty = _fade_ppm(y_ppm - y0 * PPM)
    a = (_lattice_ppm(seed, x0, y0) * (PPM - tx)
         + _lattice_ppm(seed, x1, y0) * tx) // PPM
    b = (_lattice_ppm(seed, x0, y1) * (PPM - tx)
         + _lattice_ppm(seed, x1, y1) * tx) // PPM
    return (a * (PPM - ty) + b * ty) // PPM

def _utf16_key(value: str) -> bytes:
    return value.encode("utf-16-be", "surrogatepass")

def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        items = [(unicodedata.normalize("NFC", str(k)), v) for k, v in value.items()]
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate object key after NFC normalization")
        return {k: _jsonable(v) for k, v in sorted(items, key=lambda p: _utf16_key(p[0]))}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        raise ValueError("canonical data uses scaled integers, not floats")
    return value

def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")

def stable_artifact_id(kind: str, content_sha256: str,
                       dependency_ids: tuple[str, ...],
                       producer_fingerprint: str) -> str:
    if not (kind.isascii() and kind.isalnum() and kind[0].islower()
            and kind == kind.lower()):
        raise ValueError("artifact kind must be a lowercase alphanumeric ID prefix")
    identity = canonical_bytes({
        "depends_on": list(sorted(dependency_ids)),
        "kind": kind,
        "producer_fingerprint": producer_fingerprint,
        "sha256": content_sha256,
    })
    digest = sha256(identity).hexdigest()
    return f"{kind}_{digest[:32]}"

@dataclass(frozen=True)
class AlgorithmVersions:
    terrain: str = "terrain-1"
    hydrology: str = "hydrology-1"
    climate: str = "climate-1"
    ecology: str = "ecology-1"
    history: str = "history-1"
    local_site: str = "local-site-1"
```

Example independent streams:

```python
terrain_rng = rng_for(seed, "terrain", versions.terrain)
river_rng = rng_for(seed, "hydrology", versions.hydrology)
civ_rng = rng_for(seed, "civilization", civ_id)
year_rng = rng_for(seed, "history-year", year)
person_rng = rng_for(seed, "person", person_id)
site_rng = rng_for(seed, "local-site", site_id, versions.local_site)
```

Stable IDs are content-independent identities assigned from domain and deterministic
ordinal, not display names:

```python
def stable_id(kind: str, seed: int, ordinal: int) -> str:
    raw = f"{kind}:{seed}:{ordinal}".encode("ascii")
    return f"{kind}_{sha256(raw).hexdigest()[:32]}"
```

Sort all outputs by stable ID or canonical coordinates before serialization.

## World specification

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class WorldSpec:
    master_seed: int
    width: int = 1024
    height: int = 1024
    continent_count: int = 1
    metres_per_world_cell: int = 8_000
    plate_count: int = 24
    minimum_continent_cells: int = 4_096
    history_years: int = 500
    history_ticks_per_year: int = 12
    civilization_count: int = 8
    sea_level_ppm: int = 380_000
    axial_tilt_millidegrees: int = 23_500
    erosion_passes: int = 32
    climate_relaxation_passes: int = 64
    snapshot_interval_years: int = 10
    local_site_width: int = 128
    local_site_height: int = 128
    local_z_levels: int = 32
    local_cell_millimetres: int = 2_000

    def validate(self) -> None:
        if self.width < 32 or self.height < 32:
            raise ValueError("world grid is too small")
        if self.continent_count < 1:
            raise ValueError("at least one continent is required")
        if not self.continent_count <= self.plate_count <= 256:
            raise ValueError("plate count must cover continents and be at most 256")
        if not 50_000 <= self.sea_level_ppm <= 950_000:
            raise ValueError("sea level must be within 50,000..950,000 ppm")
        if self.history_years < 0 or self.civilization_count < 1:
            raise ValueError("history and civilization counts must be nonnegative")
        if self.history_ticks_per_year != 12:
            raise ValueError("worldgen-1 requires 12 history ticks per year")
        if not 250 <= self.metres_per_world_cell <= 100_000:
            raise ValueError("world-cell scale out of range")
        if self.snapshot_interval_years != 10:
            raise ValueError("worldgen-1 requires ten-year snapshots")
        if not 0 <= self.erosion_passes <= 512:
            raise ValueError("erosion passes out of range")
        if not 8 <= self.climate_relaxation_passes <= 512:
            raise ValueError("climate relaxation passes out of range")
        if not (32 <= self.local_site_width <= 1024 and
                32 <= self.local_site_height <= 1024 and
                4 <= self.local_z_levels <= 256):
            raise ValueError("local map dimensions out of range")
```

Presets expand into explicit values before generation. The recorded effective
specification never contains an unresolved word such as `standard`.

## Authoritative data model

Use immutable records for committed facts and separate simulation state while a
domain is being built.

```python
from dataclasses import dataclass, field
from typing import Literal

BiomeId = Literal[
    "deep_ocean", "coastal_water", "tundra", "glacier", "taiga",
    "temperate_forest", "tropical_forest", "grassland", "savanna",
    "shrubland", "marsh", "swamp", "desert", "badlands",
    "hills", "mountain", "alpine_peak",
]

@dataclass(frozen=True)
class SurfaceCell:
    coordinate: Cell
    elevation_m: int
    slope_ppm: int
    plate_id: str
    temperature_mc_by_season: tuple[int, int, int, int]
    precipitation_mm_by_season: tuple[int, int, int, int]
    drainage_ppm: int
    soil_depth_mm: int
    fertility_ppm: int
    biome: BiomeId
    watershed_id: str | None
    river_id: str | None
    region_id: str
    resources: tuple[str, ...]
    hazards: tuple[str, ...]

@dataclass(frozen=True)
class River:
    id: str
    source: Cell
    mouth: Cell
    course: tuple[Cell, ...]
    discharge_litres_per_second_by_season: tuple[int, int, int, int]
    tributary_ids: tuple[str, ...]

@dataclass(frozen=True)
class Region:
    id: str
    name_key: str
    cells: tuple[Cell, ...]
    biome_mix_ppm: tuple[tuple[BiomeId, int], ...]
    carrying_capacity: int
    neighbor_ids: tuple[str, ...]
    route_costs: tuple[tuple[str, int], ...]

@dataclass(frozen=True)
class Site:
    id: str
    kind: str
    cell: Cell
    region_id: str
    founded_year: int
    owner_civilization_id: str | None
    population: int
    prosperity_ppm: int
    resource_ids: tuple[str, ...]
    local_map_id: str | None = None

@dataclass(frozen=True)
class Civilization:
    id: str
    people_id: str
    government_id: str
    capital_site_id: str
    site_ids: tuple[str, ...]
    population: int
    treasury: int
    technologies: tuple[str, ...]
    beliefs: tuple[str, ...]

@dataclass(frozen=True)
class HistoricalEvent:
    id: str
    year: int
    tick: int
    kind: str
    cause_event_ids: tuple[str, ...]
    participant_ids: tuple[str, ...]
    location_ids: tuple[str, ...]
    changes: tuple["StateChange", ...]
    tags: tuple[str, ...]

@dataclass(frozen=True)
class StateChange:
    operation: Literal["set", "add", "remove", "transfer", "destroy"]
    entity_id: str
    field: str
    before: object
    after: object

@dataclass(frozen=True)
class World:
    spec: WorldSpec
    versions: AlgorithmVersions
    cells: tuple[SurfaceCell, ...]
    rivers: tuple[River, ...]
    regions: tuple[Region, ...]
    sites: tuple[Site, ...]
    civilizations: tuple[Civilization, ...]
    events: tuple[HistoricalEvent, ...]
    local_maps: tuple["LocalMap", ...]
```

### Complete domain inventory

The logical `World` summary above does not flatten every domain into one object.
The persisted world consists of these required canonical artifacts:

```python
ArtifactKind = Literal[
    "world_spec", "seed_plan", "plates", "terrain", "geology", "hydrology",
    "climate", "soil", "biomes", "resources", "species", "ecology",
    "regions", "routes", "magic_laws", "languages", "peoples", "cultures",
    "religions", "governments", "sites", "civilizations", "persons",
    "cohorts", "economy", "history_events", "history_snapshots", "local_maps",
    "story_opportunities", "map_layers", "spatial_index", "reference_index",
    "validation_report",
]

@dataclass(frozen=True)
class ArtifactEnvelope:
    artifact_id: str
    kind: ArtifactKind
    schema_version: str
    algorithm_profile: str
    producer_version: str
    dependency_ids: tuple[str, ...]
    dependency_sha256: tuple[tuple[str, str], ...]
    parameters_sha256: str
    content_sha256: str
    record_count: int
    canonical_path: str
```

Each canonical path is unique and derived from `kind`, never user input. Content is
stored separately from the envelope so hashes cannot recursively include
themselves. Every artifact is immutable after commit.

### Entity record requirements

Every entity record must contain:

- stable `id` and explicit type;
- creation/foundation/birth year when time-dependent;
- location or containment references where spatial;
- provenance fact/event IDs;
- typed attributes with units;
- sorted outgoing reference IDs;
- no embedded mutable runtime state.

The following additional records close the required world schema:

```python
@dataclass(frozen=True)
class Plate:
    id: str
    center: Cell
    continental: bool
    velocity_x_ppm: int
    velocity_y_ppm: int
    crust_age_millions_years: int

@dataclass(frozen=True)
class ResourceDeposit:
    id: str
    material_id: str
    cell_indices: tuple[int, ...]
    minimum_depth_m: int
    maximum_depth_m: int
    grade_ppm: int
    original_quantity: int
    remaining_quantity: int

@dataclass(frozen=True)
class Species:
    id: str
    trophic_level: str
    habitat_biomes: tuple[BiomeId, ...]
    temperature_range_mc: tuple[int, int]
    food_species_ids: tuple[str, ...]
    reproduction_ppm: int
    mortality_ppm: int
    domestication_ppm: int

@dataclass(frozen=True)
class Cohort:
    id: str
    site_id: str
    people_id: str
    age_band: str
    count: int
    susceptible: int
    exposed: int
    infected: int
    recovered: int

@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Literal["error", "warning"]
    artifact_id: str
    entity_id: str | None
    json_pointer: str
    message_parameters: tuple[tuple[str, object], ...]

@dataclass(frozen=True)
class ValidationReport:
    profile: str
    artifact_ids: tuple[str, ...]
    validator_versions: tuple[tuple[str, str], ...]
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
```

Warnings may describe unusual but valid worlds. Any error prevents downstream
commit or final publication.

Arrays may be stored in a compact binary form, but their logical schema and hashes
remain explicit. The complete event ledger is never replaced by prose summaries.

## Generation dependency graph

```text
WorldSpec + master seed + algorithm versions
  │
  ├─► plate field ─► elevation ─► erosion ─► slope/geology
  │                                      │
  │                                      ├─► underground strata/resources
  │                                      └─► hydrology/watersheds/rivers/lakes
  │
  ├─► latitude/tilt/winds ───────────────► climate/seasons/weather
  │                                                     │
  └─────────────────────────────────────────────────────┤
                                                        ▼
                                              soil/biomes/ecology
                                                        │
                                                        ▼
                                             regions/travel graph
                                                        │
                                                        ▼
                                         peoples/sites/civilizations
                                                        │
                                                        ▼
                                             historical simulation
                                                        │
                              ┌─────────────────────────┴──────────────┐
                              ▼                                        ▼
                       all site maps                       story-facing views
```

Each arrow is a declared dependency. Changing history length invalidates history
and downstream views, but not terrain. Changing sea level invalidates hydrology,
climate-dependent domains, settlement, and history.

## Stage 1: plates, landmasses, and elevation

Do not generate elevation from noise alone. Noise adds texture, while continental
shape and mountain systems come from plate-like fields.

1. Place deterministic plate seeds with minimum spacing.
2. Assign every cell to its nearest plate using a wrapped or bounded metric.
3. Give each plate a deterministic motion vector and continental/oceanic type.
4. Classify neighboring plate boundaries as convergent, divergent, or transform.
5. Construct broad continental masks for the requested continent count.
6. Add uplift at convergent boundaries, rift depressions at divergent boundaries,
   and volcanic arcs where appropriate.
7. Add multi-octave noise only as bounded detail.
8. Apply deterministic thermal and hydraulic erosion.
9. Normalize elevation while preserving the configured sea level and continent
   count.

```python
from typing import Protocol

def fractal_noise_ppm(x: int, y: int, seed: int, octaves: int = 5) -> int:
    total = 0
    amplitude = PPM
    frequency = 1
    weight = 0
    for octave in range(octaves):
        sample = noise2_ppm(x * frequency * PPM, y * frequency * PPM,
                            derive_seed(seed, "octave", octave))
        total += amplitude * sample // PPM
        weight += amplitude
        amplitude //= 2
        frequency *= 2
    return total * PPM // weight

class BoundaryField(Protocol):
    def convergence_ppm(self, cell: Cell) -> int: ...
    def divergence_ppm(self, cell: Cell) -> int: ...

def raw_elevation(cell: Cell, plate: Plate, boundary: BoundaryField,
                  seed: int) -> int:
    base = 650_000 if plate.continental else 220_000
    uplift = boundary.convergence_ppm(cell) * 350_000 // PPM
    rift = boundary.divergence_ppm(cell) * 200_000 // PPM
    texture = fractal_noise_ppm(cell.x, cell.y, seed) * 100_000 // PPM
    return clamp(base + uplift - rift + texture, 0, PPM)
```

Required invariants:

- every cell has exactly one plate;
- requested landmass constraints are satisfied;
- elevation is finite and within range;
- coastlines separate land and ocean consistently;
- mountain chains correlate with uplift fields rather than isolated noise specks;
- no iteration order changes canonical elevation bytes.

## Stage 2: hydrology

Hydrology is derived from elevation, not independently painted noise.

1. Fill or identify depressions using a priority-flood algorithm.
2. Compute deterministic flow direction with a declared tie-break order.
3. Accumulate upstream catchment area.
4. Select river sources using accumulation, rainfall, elevation, and seasonality.
5. Trace rivers downhill until ocean, lake, or an existing larger river.
6. Form lakes at valid basins and record outlets or endorheic status.
7. Compute seasonal discharge, floodplain width, wetlands, and aquifer recharge.
8. Derive salinity from ocean connection, evaporation, and basin closure.

```python
NEIGHBOR_ORDER = ((0, -1), (-1, 0), (1, 0), (0, 1),
                  (-1, -1), (1, -1), (-1, 1), (1, 1))

def flow_target(cell: Cell, filled_height: dict[Cell, int]) -> Cell | None:
    candidates: list[tuple[int, int, Cell]] = []
    for rank, (dx, dy) in enumerate(NEIGHBOR_ORDER):
        neighbor = Cell(cell.x + dx, cell.y + dy)
        if neighbor in filled_height:
            candidates.append((filled_height[neighbor], rank, neighbor))
    if not candidates:
        return None
    height, _, target = min(candidates)
    return target if height <= filled_height[cell] else None

def trace_river(source: Cell, flow: dict[Cell, Cell | None],
                ocean: set[Cell]) -> tuple[Cell, ...]:
    course: list[Cell] = []
    seen: set[Cell] = set()
    current: Cell | None = source
    while current is not None and current not in seen:
        course.append(current)
        if current in ocean:
            return tuple(course)
        seen.add(current)
        current = flow[current]
    raise ValueError(f"river from {source} does not terminate validly")
```

Required invariants:

- a river never climbs above the filled hydrological surface;
- every river terminates in ocean, lake, or a larger river;
- tributary graphs are acyclic;
- lakes have a valid basin and at most one canonical outlet;
- watershed cells drain to their declared sink;
- river crossings influence routes, settlement, agriculture, and history.

## Stage 3: climate and weather

Climate should respond to latitude, elevation, ocean distance, winds, and terrain.
For each of four seasons:

1. derive solar energy from latitude and axial tilt;
2. reduce temperature by elevation lapse rate;
3. moderate coastal cells using ocean temperature;
4. advect moisture along prevailing wind bands;
5. precipitate on windward slopes and create leeward rain shadows;
6. accumulate snow where temperature permits;
7. derive storm, drought, flood, wildfire, and freeze probabilities;
8. aggregate seasonal values into climate classifications.

```python
def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))

def cos_lookup_ppm(angle_mdeg: int) -> int:
    """Deterministic Bhaskara-I cosine approximation in parts per million."""
    angle = angle_mdeg % 360_000
    if angle > 180_000:
        angle = 360_000 - angle
    sign = 1 if angle <= 90_000 else -1
    sine_angle = 90_000 - angle if angle <= 90_000 else angle - 90_000
    x = sine_angle
    product = x * (180_000 - x)
    denominator = 40_500_000_000 - product
    magnitude = 4 * product * PPM // max(1, denominator)
    return sign * magnitude

def seasonal_temperature_mc(latitude_mdeg: int, elevation_m: int,
                            season_phase_ppm: int, axial_tilt_mdeg: int,
                            continentality_ppm: int) -> int:
    # COS_PPM is a frozen lookup indexed by normalized millidegrees.
    solar_mc = 30_000 * cos_lookup_ppm(
        latitude_mdeg - axial_tilt_mdeg * season_phase_ppm // PPM
    ) // PPM
    lapse_mc = 6_500 * elevation_m // 1_000
    swing_mc = 12_000 * continentality_ppm // PPM * season_phase_ppm // PPM
    return solar_mc - lapse_mc + swing_mc - 5_000

def orographic_precipitation(incoming_mg_m2: int, rise_m: int,
                             temperature_mc: int) -> tuple[int, int]:
    condensation_ppm = clamp_int(rise_m * PPM // 1_800, 0, 850_000)
    temperature_factor_ppm = clamp_int((temperature_mc + 20_000) * PPM // 50_000,
                                       100_000, PPM)
    rain = incoming_mg_m2 * condensation_ppm // PPM
    rain = rain * temperature_factor_ppm // PPM
    return rain, incoming_mg_m2 - rain
```

The approximation and its integer rounding are part of the climate algorithm
version. A future profile may replace it only with new golden vectors.

Weather events are deterministic time-series events derived from the climate band,
year, season, and cell/region seed. Climate defines probability and magnitude;
weather records actual storms, droughts, and unusual winters that can affect
history.

## Stage 4: geology, soil, resources, and ecology

Geology derives from plate type, boundary, uplift, erosion, and volcanic history.
Resources occur in deposits with shape, grade, estimated quantity, depth, and
access cost—not independent per-cell coin flips.

Examples:

- iron in banded formations or hydrothermal zones;
- copper and gold near intrusive/volcanic systems;
- coal in old sedimentary basins;
- salt in evaporated closed basins;
- fertile alluvium in floodplains;
- clay in low-energy depositional areas;
- timber and fibers from biome productivity;
- rare fantasy materials tied to explicit geological or magical anomalies.

```python
@dataclass(frozen=True)
class Deposit:
    id: str
    material: str
    cells: tuple[Cell, ...]
    depth_m: tuple[int, int]
    grade_ppm: int
    quantity: int
    discovered_year: int | None

@dataclass(frozen=True)
class GeologyFactors:
    sedimentary_ppm: int
    ancient_biomass_ppm: int
    hydrothermal_ppm: int
    volcanic_arc_ppm: int
    closed_basin_ppm: int

@dataclass(frozen=True)
class ClimateFactors:
    aridity_ppm: int

def resource_suitability(material: str, geology: GeologyFactors,
                         climate: ClimateFactors) -> int:
    if material == "coal":
        return mul_ppm(geology.sedimentary_ppm, geology.ancient_biomass_ppm)
    if material == "copper":
        return max(geology.hydrothermal_ppm, geology.volcanic_arc_ppm) * 900_000 // PPM
    if material == "salt":
        return mul_ppm(geology.closed_basin_ppm, climate.aridity_ppm)
    return 0
```

Biome classification uses a decision table whose conditions are mutually exclusive
and ordered explicitly. It consumes climate, elevation, soil, drainage, salinity,
and disturbance. Random variation may choose among equally valid sub-biomes but
cannot override a physical incompatibility.

Ecology then produces habitats, productivity, food webs, species ranges, migration
corridors, domestication candidates, and carrying capacity. The simulation can
track species at archetype level globally and create named individuals only when
history or narrative needs them.

## Stage 5: regions and travel graph

Regions are coherent connected areas useful to people and stories. Build them from
watersheds, terrain barriers, biome similarity, coastlines, and travel cost, then
split or merge until size and connectivity constraints hold.

The travel graph connects regions and sites by feasible edges:

- roads prefer low slope and dry ground;
- passes cross mountain barriers at locally favorable saddles;
- river travel follows navigable discharge and direction/cost rules;
- sea lanes connect ports based on distance, currents, seasonal storms, and known
  navigation technology;
- tunnels require a construction event and appropriate technology;
- winter routes may differ from summer routes.

```python
@dataclass(frozen=True)
class RouteEdge:
    id: str
    start_id: str
    end_id: str
    mode: Literal["road", "trail", "river", "sea", "pass", "tunnel"]
    cells: tuple[Cell, ...]
    cost_by_season: tuple[int, int, int, int]
    capacity: int
    founded_year: int

def route_cost(cell: SurfaceCell, season: int) -> int:
    slope_cost = PPM + cell.slope_ppm * 8
    biome_cost = {
        "grassland": 1_000_000, "temperate_forest": 1_400_000,
        "swamp": 4_000_000, "desert": 2_200_000,
        "mountain": 6_000_000, "glacier": 8_000_000,
    }.get(cell.biome, 2_000_000)
    weather_cost = PPM + cell.precipitation_mm_by_season[season] * 1_000
    return mul_ppm(mul_ppm(slope_cost, biome_cost), weather_cost)
```

## Stage 6: peoples, governments, and cultures

A people definition is data, not hard-coded branching:

```python
@dataclass(frozen=True)
class PeopleTemplate:
    id: str
    preferred_biomes: tuple[BiomeId, ...]
    disliked_hazards: tuple[str, ...]
    subsistence: tuple[str, ...]
    strength: int
    body_size: int
    reproduction_rate_ppm: int
    migration_rate_ppm: int
    social_forms: tuple[str, ...]

@dataclass(frozen=True)
class GovernmentTemplate:
    id: str
    authority: str
    succession: str
    centralization_ppm: int
    militarization_ppm: int
    expansionism_ppm: int
    trade_openness_ppm: int
    reform_pressure_ppm: int
    technology_modifier_ppm: int
```

Culture is generated from environment and history rather than race stereotypes.
Its food, architecture, clothing, instruments, transport, rituals, taboos, and
metaphors should reflect available materials, climate, religion, neighbors, past
trauma, and trade. A government influences decisions but does not predetermine
every event.

Flags, heraldry, scripts, and names can be composed from versioned grammars:

- choose a deterministic palette with contrast constraints;
- combine background division and overlay motif;
- attach motif meanings to cultural beliefs or history;
- store vector-like pattern parameters, not only a raster;
- generate display names from phoneme/morpheme grammars while stable IDs remain
  language-independent.

### Embedded `worldgen-1` content registry

The profile contains the following minimum registry. Implementations may add
entries only by creating a new content-registry version whose hash participates in
the run fingerprint. Numeric suitability modifiers use PPM.

| People archetype | Preferred environments | Subsistence strengths | Social forms |
|---|---|---|---|
| highland delvers | mountain, hills, underground | mining, masonry, fungi, trade | clan, guild, monarchy, council |
| river-valley settlers | grassland, forest, river, coast | farming, herding, navigation | monarchy, republic, theocracy, league |
| forest stewards | temperate/tropical forest | forestry, gathering, horticulture | council, lineage, sacred custodianship |
| steppe confederates | grassland, savanna, shrubland | herding, hunting, caravan trade | tribe, confederation, elective war leadership |
| marsh communities | marsh, swamp, delta | fishing, reeds, medicine, river trade | village league, priesthood, elder council |
| wasteland survivors | desert, badlands, volcanic frontier | caravan trade, salvage, extraction | clan, fortress state, cult polity |

These are environmental/cultural starting distributions, not fixed biological
destinies. History can move, merge, split, assimilate, reform, or specialize them.

Government registry:

| ID | Authority | Succession | Centralization | Militarization | Trade openness |
|---|---|---|---:|---:|---:|
| absolute-monarchy | one sovereign | hereditary with crisis rules | 850k | 500k | 400k |
| constitutional-monarchy | sovereign and assembly | hereditary + confirmation | 650k | 400k | 600k |
| republic | elected offices | periodic election | 600k | 350k | 750k |
| oligarchy | property/guild elite | internal selection | 700k | 400k | 700k |
| theocracy | religious office | doctrinal appointment | 750k | 450k | 350k |
| military-state | command hierarchy | appointment/coup | 900k | 850k | 250k |
| tribal-council | kin/community council | custom and acclaim | 300k | 400k | 500k |
| confederation | member polities | delegated/elective | 250k | 450k | 700k |

Minimum material families are water, soil, clay, sand, salt, timber, fiber, food,
medicinal plant, hide, bone, common stone, hard stone, decorative stone, coal/charcoal,
iron ore, copper ore, tin ore, silver ore, gold ore, gems, iron, bronze, steel, and
one generated rare magical material. Every concrete material declares density,
hardness, melting range, fuel value, edibility, renewability, geology/habitat, and
base value in integer units.

Minimum production recipes are grain→food, raw food→meal, timber→lumber,
fiber/hide→cloth/leather, clay→ceramic, ore+fuel→metal, metal→tool, material→weapon,
material→armor, stone/timber→building, herb→medicine, and magical
material+rite→relic. Inputs, outputs, waste, labor, skill, building, fuel, and
technology prerequisites are explicit; no recipe has a negative or empty input.

The supernatural registry selects one to three sources from divine covenant,
ancestral pact, spirit ecology, blood sacrifice, dream, rune, alchemy, corruption,
or celestial resonance. Every selected source generates at least one cost and one
hard prohibition. Resurrection, time reversal, creation of unlimited matter, and
unbounded mind control are prohibited in `worldgen-1`; individual laws may not
enable them.

## Stage 7: settlement placement and growth

Settlement suitability combines habitability and strategic value:

```python
@dataclass(frozen=True)
class NearbyFeatures:
    fresh_water_metres: int
    ecological_productivity_ppm: int
    route_centrality: int
    defensibility: int
    required_resource_coverage: int
    hazard_pressure: int
    existing_settlement_pressure: int

def settlement_score(cell: SurfaceCell, people: PeopleTemplate,
                     nearby: NearbyFeatures) -> int:
    biome = PPM if cell.biome in people.preferred_biomes else 350_000
    water = PPM if cell.river_id or nearby.fresh_water_metres < 8_000 else 200_000
    food = mul_ppm(cell.fertility_ppm, nearby.ecological_productivity_ppm)
    trade = nearby.route_centrality
    defense = nearby.defensibility
    resources = nearby.required_resource_coverage
    hazard = nearby.hazard_pressure
    crowding = nearby.existing_settlement_pressure
    return 2 * biome + 2 * water + food + trade + defense + resources - hazard - crowding
```

Initial capitals use deterministic weighted selection with minimum separation.
Sites receive carrying capacity from food, water, land, sanitation, technology,
trade, and recent shocks.

A useful bounded population update is:

```python
def next_population(population: int, capacity: int, annual_rate_ppm: int,
                    migration: int, deaths_from_events: int) -> int:
    if capacity <= 0:
        return max(0, population + migration - deaths_from_events)
    unused_capacity_ppm = max(0, capacity - population) * PPM // capacity
    growth = population * annual_rate_ppm // PPM
    growth = growth * unused_capacity_ppm // PPM
    return max(0, population + growth + migration - deaths_from_events)
```

Expansion creates a site only when pressure, resources, travel reach, political
capacity, and a feasible destination all exist. The origin pays colonists and
supplies; population cannot be duplicated. New roads or forts require explicit
cost and events.

Prosperity should be a derived ledger value, not a decorative noise layer:

```text
production value
+ trade balance
+ secure food reserve
+ infrastructure benefit
- upkeep
- scarcity
- conflict loss
- disaster loss
= change in stored wealth
```

## Stage 8: economy and production

Resources flow through recipes and routes. A recipe declares inputs, outputs,
labor, skill, infrastructure, energy, duration, and waste.

```python
@dataclass(frozen=True)
class Recipe:
    id: str
    inputs: tuple[tuple[str, int], ...]
    outputs: tuple[tuple[str, int], ...]
    labor_days: int
    required_skill: str
    minimum_skill: int
    required_building: str
    fuel: tuple[str, int] | None = None

@dataclass
class Stockpile:
    quantities: dict[str, int] = field(default_factory=dict)

    def can_consume(self, recipe: Recipe, batches: int) -> bool:
        return all(self.quantities.get(item, 0) >= amount * batches
                   for item, amount in recipe.inputs)

    def apply(self, recipe: Recipe, batches: int) -> None:
        if not self.can_consume(recipe, batches):
            raise ValueError("production would create resources from nothing")
        for item, amount in recipe.inputs:
            self.quantities[item] -= amount * batches
        for item, amount in recipe.outputs:
            self.quantities[item] = self.quantities.get(item, 0) + amount * batches
```

Track conservation where appropriate. Food can spoil based on time and storage
temperature. Mines deplete deposits. War destroys or transfers inventory. Trade
moves actual quantities and pays transport cost. Shortage affects health, migration,
prices, policy, and conflict probability.

## Stage 9: history as a state machine

History advances in deterministic ticks—monthly for economics and yearly for major
policy is a practical split. Each tick follows the same order:

```text
1. Apply scheduled natural events.
2. Update harvests, production, decay, consumption, and trade.
3. Update population, health, migration, and settlement pressure.
4. Evaluate construction, exploration, and discovery proposals.
5. Evaluate diplomacy, religion, internal politics, and succession.
6. Resolve raids, wars, sieges, and territorial changes.
7. Apply deaths, destruction, transfers, and long-term consequences.
8. Emit events and validate conservation/reference invariants.
9. Commit the ledger batch and periodic snapshot atomically.
```

Proposals are collected first, sorted by stable priority and ID, then resolved.
This prevents iteration order or parallel completion from choosing history.

```python
@dataclass(frozen=True, order=True)
class Proposal:
    priority: int
    actor_id: str
    kind: str
    target_id: str
    payload: tuple[tuple[str, object], ...]

def simulate_year(state: "MutableHistoryState", year: int,
                  master_seed: int) -> tuple[HistoricalEvent, ...]:
    proposals: list[Proposal] = []
    for civ_id in sorted(state.civilizations):
        rng = rng_for(master_seed, "civ-year", civ_id, year)
        proposals.extend(propose_actions(state, civ_id, year, rng))

    events: list[HistoricalEvent] = []
    for ordinal, proposal in enumerate(sorted(proposals)):
        if preconditions_hold(state, proposal):
            event = resolve_proposal(state, proposal, year, ordinal, master_seed)
            apply_event_exactly_once(state, event)
            events.append(event)
    validate_history_state(state)
    return tuple(sorted(events, key=lambda e: (e.year, e.tick, e.id)))
```

War is not triggered merely because two sites are close. It requires contact,
tension, motive, political capacity, military supply, and a decision. Armies have
population source, size, location, supply, movement route, losses, and objective.
Peace changes relationships and may transfer territory, wealth, hostages, or law.

Every event must answer:

- What prior state or event caused it?
- Who participated and were they alive/active?
- Where did it occur and could participants reach it?
- Which exact state changed?
- Was the change applied once?
- What durable consequence can later systems observe?

## Stage 10: people and relationships

Simulate all populations statistically, but instantiate named people for rulers,
religious figures, commanders, inventors, explorers, victims, founders, witnesses,
and story-relevant households.

```python
@dataclass
class PersonState:
    id: str
    born_year: int
    died_year: int | None
    site_id: str
    civilization_id: str
    needs_ppm: dict[str, int]
    skills: dict[str, int]
    traits_ppm: dict[str, int]
    relationships_ppm: dict[str, int]
    health_ppm: int = PPM
    stress_ppm: int = 0
    trauma_ppm: int = 0

def update_person(person: PersonState, food_available: bool,
                  social_support_ppm: int, danger_ppm: int) -> None:
    food_delta = 80_000 if food_available else -150_000
    person.needs_ppm["food"] = clamp_int(person.needs_ppm["food"] + food_delta, 0, PPM)
    person.stress_ppm = clamp_int(
        person.stress_ppm + danger_ppm // 10 - social_support_ppm // 25, 0, PPM
    )
    if person.needs_ppm["food"] < 100_000:
        person.health_ppm = clamp_int(person.health_ppm - 50_000, 0, PPM)
```

Needs and personality influence proposals; they do not directly overwrite world
facts. Relationships have causes: kinship, aid, betrayal, rivalry, shared belief,
command, trade, or witnessed events. Store both value and significant changes so
the eventual story can explain them.

## Stage 11: local 3D maps for every registered site

A local map derives boundary conditions from its site's macro cell:

- surface elevation, slope, river/lake/coast geometry;
- biome, soil, climate, seasonal water table, and vegetation;
- geological strata, faults, caves, deposits, and magma likelihood;
- settlement footprint, age, culture, materials, technology, and damage history;
- roads and gates aligned with macro routes;
- ruins and scars corresponding to recorded events.

```python
@dataclass(frozen=True)
class LocalTile:
    coordinate: LocalCell
    material: str
    shape: Literal["empty", "floor", "wall", "ramp", "stair", "water", "magma"]
    temperature_mc: int
    liquid_depth: int
    stability_ppm: int
    deposit_id: str | None
    construction_id: str | None

@dataclass(frozen=True)
class LocalMap:
    id: str
    site_id: str
    width: int
    height: int
    z_levels: int
    tiles: tuple[LocalTile, ...]
```

Generation order:

1. interpolate macro elevation across the local grid;
2. extrude geological strata downward;
3. carve caves using connected fields and enforce entrances/containment;
4. insert river, coast, aquifer, and magma boundary conditions;
5. place settlement roads and parcels;
6. generate buildings from cultural grammar and historical construction dates;
7. apply recorded fires, floods, sieges, collapses, rebuilding, and abandonment;
8. validate passability, support, liquids, route alignment, and macro consistency.

Use A* or hierarchical pathfinding only after legal movement edges are defined.
Vertical movement requires ramps, stairs, ladders, safe slopes, or an explicit fall;
two empty tiles alone do not imply vertical travel.

Local physics may simulate fluid flow, heat, collapse, and decay during generation,
but it must converge to a validated snapshot. Runtime simulation is not required to
read a story.

## Stage 12: story opportunity extraction

The generator does not write the story. It emits factual opportunity records:

```python
@dataclass(frozen=True)
class StoryOpportunity:
    id: str
    kind: str
    location_ids: tuple[str, ...]
    faction_ids: tuple[str, ...]
    person_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    pressure: str
    stakes: tuple[str, ...]
    constraints: tuple[str, ...]
    possible_revelation_ids: tuple[str, ...]
    score_ppm: int
```

Candidate rules include:

- contested mine + recent depletion + militarized neighbors;
- ruined capital + disputed succession + surviving heir;
- river diversion + downstream famine + religious taboo;
- mountain pass + winter closure + stranded army;
- extinct creature reports + unexplained livestock deaths;
- trade city + plague + closed gates + smuggling network;
- old battlefield + unburied dead + new road construction;
- refugee district + hostile law + patron with divided loyalties.

Score opportunities for causal density, involved factions, spatial reachability,
unresolved pressure, available witnesses, visual distinction, and branch potential.
Do not select an impossible route or invent a major kingdom solely for a premise.

## Micro-to-macro and macro-to-micro reconciliation

Macro facts constrain local generation:

- climate constrains clothing, crops, buildings, and travel season;
- geology constrains stone, ore, caves, and construction material;
- routes constrain trade, armies, migration, and story movement;
- population constrains armies, labor, food use, and settlement scale;
- history constrains ruins, borders, beliefs, relationships, and memories.

Micro outcomes can aggregate upward only through explicit events:

- a local mine changes regional resource availability after discovery/extraction;
- a person's succession changes government through a succession event;
- a destroyed bridge changes route cost through a destruction event;
- a local plague changes population and migration through recorded consequences;
- a newly invented technique changes production only after diffusion events.

```python
def reconcile_local_site(site: Site, local: LocalMap,
                         macro: SurfaceCell, routes: tuple[RouteEdge, ...]) -> list[str]:
    errors: list[str] = []
    if local.site_id != site.id:
        errors.append("local map belongs to another site")
    if any(t.material == "granite" for t in local.tiles) and "granite" not in macro.resources:
        errors.append("local geology introduces unavailable granite")
    route_cells = {c for r in routes if site.id in (r.start_id, r.end_id) for c in r.cells}
    if routes and not route_cells:
        errors.append("site route has no macro geometry")
    return errors
```

Small local entities may be added later if they are contained by an existing site
or region, use available materials and culture, do not change an authoritative
major event, and receive stable provenance marking them as local enrichment.

## Validation suite

### Structural validation

- unique stable IDs and canonical ordering;
- all references resolve and types match;
- coordinates are in bounds and declare their scale;
- values are finite and within declared ranges;
- complete domain inventory and dependency hashes;
- serialization round-trip preserves canonical bytes.

### Physical validation

- continent count and land fraction satisfy the effective specification;
- coast, plate, elevation, slope, and region coverage are complete;
- hydrology terminates, basins are coherent, and rivers do not cycle;
- seasonal climate values and biome/resource combinations are plausible;
- deposits have legal geology and quantities;
- region adjacency is symmetric and every region is connected;
- route geometry is contiguous, traversable, and joins declared endpoints.

### Civilization validation

- sites occupy suitable, unclaimed coordinates at foundation time;
- population changes conserve migrants and respect recorded births/deaths;
- armies, labor, and colonists come from populations rather than appearing;
- production consumes inputs before creating outputs;
- trade uses feasible routes and transfers actual inventory;
- territory ownership is valid and non-overlapping where exclusive;
- governments, rulers, sites, and cultures belong to valid civilizations.

### History validation

- event order is total by `(year, tick, id)`;
- causes precede consequences;
- participants exist and are active at the event time;
- locations exist and are reachable where travel is required;
- every `before` value matches current state;
- every change is applied exactly once;
- snapshot replay equals the committed state;
- destroyed/dead entities cannot act without an explicit valid rule;
- full ledger remains present even if all summaries are discarded.

### Local-map validation

- tile bounds, material, shape, liquid, temperature, and stability are legal;
- settlements have a passable connection to each declared macro route;
- buildings fit parcels and cultural/material constraints;
- stairs/ramps align across z-levels;
- fluids cannot begin outside declared water/aquifer sources;
- event scars correspond to real historical event IDs;
- local facts do not contradict macro geology, climate, ownership, or history.

## Determinism and parallelism

Parallelize pure cell/domain calculations, never decisions whose result depends on
arrival order. Workers return `(stable_key, result)` pairs; the coordinator sorts
and commits them canonically.

```python
from collections.abc import Callable, Iterable
from concurrent.futures import Executor
from typing import TypeVar

K = TypeVar("K")
V = TypeVar("V")

def deterministic_map(executor: Executor, fn: Callable[[K], V],
                      keys: Iterable[K]) -> tuple[tuple[K, V], ...]:
    ordered = tuple(sorted(keys))
    futures = {key: executor.submit(fn, key) for key in ordered}
    return tuple((key, futures[key].result()) for key in ordered)
```

Required comparisons:

- repeated generation gives identical domain bytes;
- one worker and many workers give identical bytes;
- output directory and machine-local paths do not change content;
- procedural domains match across supported operating systems;
- resume and uninterrupted generation match;
- changing one domain parameter invalidates exactly its dependency closure;
- diagnostics identify the first differing artifact/path/value.

Floating-point algorithms require special care. Prefer fixed-point integers for
canonical elevation, rainfall, temperature, costs, and probabilities. If floats
are used internally, define rounding at every committed boundary and reject NaN or
infinity.

## Map layers and indexes

Canonical map data is geometry and scalar data, not a screenshot. Required layers
are elevation, plates/boundaries, coast, watersheds, rivers/lakes, seasonal
temperature, seasonal precipitation, drainage, soils, biomes, resources, hazards,
regions, sites, territories, roads, sea routes, historical borders, and story
locations.

Raster previews are derived with a frozen render profile:

```python
@dataclass(frozen=True)
class RenderProfile:
    id: str
    pixels_per_cell: int
    biome_colors: tuple[tuple[str, str], ...]
    river_width_breaks: tuple[tuple[int, int], ...]
    label_priority: tuple[str, ...]
    font_asset_sha256: str

@dataclass(frozen=True)
class MapFeature:
    id: str
    layer: str
    geometry_type: Literal["point", "polyline", "polygon", "grid"]
    coordinates: tuple[int, ...]
    source_entity_ids: tuple[str, ...]
```

Draw order is profile order followed by feature ID. Labels sort by
`(-priority, entity_id)`, occupy integer bounding boxes, and are accepted only when
they do not overlap a previously accepted higher-priority label. A raster pixel
must trace back to layer and source entity IDs through the map index.

Required indexes map cells to regions, watersheds, biomes, territories, deposits,
hazards, and sites; entities to outgoing/incoming references; events to causes,
consequences, participants, and locations; regions/sites to seasonal route edges;
facts to source/reveal metadata; and display names to all matching stable IDs.
Indexes are canonical, hash-verified, and rebuildable from authoritative artifacts.

## Stage contracts and failure semantics

| Stage | Required inputs | Algorithm family | Required validation | Failure behavior |
|---|---|---|---|---|
| specification | user configuration | strict parse/default expansion | ranges, cross-field/resource preflight | abort |
| seed plan | specification | SHA-256 domain derivation | uniqueness/golden vectors | abort |
| plates | spec, seed plan | spaced centers/Voronoi/motion | coverage, count, adjacency | bounded retry, then abort |
| terrain | plates | fixed-point uplift/noise/erosion | bounds, continent count, mass ledger | bounded retry, then abort |
| geology | plates, terrain | strata/boundary rules | full coverage, legal strata | abort |
| hydrology | terrain, geology | priority flood/flow accumulation | termination, acyclic basins/rivers | abort |
| climate | terrain, hydrology | seasonal energy/moisture relaxation | convergence, ranges, conservation bounds | abort |
| soil/biomes | geology, hydrology, climate | erosion/deposition/decision table | total classification, compatibility | abort |
| resources/ecology | physical domains | suitability fields/food web | geology, habitat, energy/capacity | abort |
| regions/routes | physical/ecology | multi-source Dijkstra/A* | connectivity, adjacency, feasibility | abort |
| magic/cosmology | spec, seed plan, physical facts | registry composition | legal/payable laws | abort |
| language/culture/religion | people, environment, magic | grammar/rule composition | reference/material/belief consistency | bounded entity retry, then abort |
| sites/civilizations | regions, routes, resources, cultures | scored placement/state creation | suitability, separation, conservation | bounded retry, then abort |
| history | all prior authoritative domains | monthly proposal/state transitions | replay, causes, conservation, references | resume committed tick or abort |
| local maps | site and macro boundary facts | strata/caves/settlement/event application | macro, physics, path consistency | bounded site retry, then abort |
| opportunities | all facts/history | deterministic rule scoring | references/reachability/no new facts | discard invalid candidate; abort if none |
| maps/indexes | committed domains | deterministic derivation | source coverage/rebuild equality | abort |
| acceptance | every required artifact | composed validators | zero errors/complete provenance | reject publication |

A retry uses unchanged semantic inputs and a declared attempt-derived seed. It
never mutates a committed dependency. `worldgen-1` permits four attempts for
plate/terrain, language/name, civilization placement, and required local maps;
other stages are single-attempt deterministic computations.

Stable diagnostic codes are `WG-SPEC-001`, `WG-SEED-001`, `WG-TERRAIN-001`,
`WG-HYDRO-001`, `WG-CLIMATE-001`, `WG-ECO-001`, `WG-SPACE-001`, `WG-CIV-001`,
`WG-HISTORY-001`, `WG-LOCAL-001`, `WG-INDEX-001`, `WG-DETERMINISM-001`, and
`WG-PERSIST-001`. Each identifies stage, artifact/entity, JSON pointer or cell,
algorithm profile, seed domain, and bounded expected/actual values. A diagnostic
never silently repairs committed state.

## Persistence and full-data retention

Commit each domain as an immutable artifact with:

- artifact ID and schema version;
- producing algorithm/version;
- master/domain seed identifiers;
- exact effective parameters;
- dependency artifact IDs and hashes;
- canonical content hash;
- counts, bounds, and validation status.

Large grids use chunked arrays and indexes. History uses a chunked event ledger
plus fixed-cadence snapshots. Every registered site's local map uses sparse
chunks. Chunks have no inner compression; deterministic ZIP compression is the
only compression layer, and every uncompressed chunk is independently hashed.

Nothing is removed merely because the story does not reference it. A story-facing
index points into the full data; it is not the only copy. Mutable reader saves and
conversation history are never part of the generated immutable world.

### Canonical encoding

Structured records use RFC 8785 JCS UTF-8 JSON with Unicode normalized to NFC
before canonicalization, JCS UTF-16 object-member ordering, no trailing newline,
minimal base-10 integers, no floating-point canonical facts, and arrays sorted by
their schema-declared keys. Duplicate keys/IDs, `-0`, NaN, infinity, and unpaired
surrogates are errors. Timestamps and machine paths are excluded. SHA-256 values
are lowercase 64-character hexadecimal strings.

Large integer grids use row-major signed little-endian integers of a
schema-declared width. Chunks have frozen dimensions except at the outer edges and
sort by `(chunk_y, chunk_x, layer)`. Every chunk is hashed; the artifact content
hash covers the ordered inventory of canonical paths, sizes, and hashes.

Commit sequence is temporary write, flush, file sync, atomic rename, directory
sync, then envelope/checkpoint transaction. Resume verifies content and dependency
hashes before reuse.

### Snapshot and replay

A snapshot contains all mutable simulation tables at the end of a declared tick,
the last event ID, and event-prefix hash. It is a cache, not independent authority.
Replay from genesis or any verified snapshot through the remaining ledger must
produce byte-identical state. Snapshot mismatch invalidates the snapshot; ledger
mismatch invalidates history and every downstream artifact.

## Complete pipeline interface

```python
from typing import Protocol, TypeVar, Generic

T = TypeVar("T")

@dataclass(frozen=True)
class Artifact(Generic[T]):
    id: str
    kind: str
    schema_version: str
    algorithm_version: str
    dependency_ids: tuple[str, ...]
    producer_fingerprint: str
    content_sha256: str
    value: T

class Stage(Protocol[T]):
    name: str
    schema_version: str
    algorithm_version: str
    producer_fingerprint: str

    def generate(self, spec: WorldSpec, dependencies: dict[str, Artifact[object]]) -> T: ...
    def validate(self, value: T, dependencies: dict[str, Artifact[object]]) -> tuple[str, ...]: ...

def run_stage(stage: Stage[T], spec: WorldSpec,
              dependencies: dict[str, Artifact[object]]) -> Artifact[T]:
    value = stage.generate(spec, dependencies)
    errors = stage.validate(value, dependencies)
    if errors:
        raise ValueError({"stage": stage.name, "errors": errors})
    canonical = canonical_bytes(value)
    content_sha256 = sha256(canonical).hexdigest()
    dependency_ids = tuple(sorted(a.id for a in dependencies.values()))
    return Artifact(
        id=stable_artifact_id(
            stage.name, content_sha256, dependency_ids, stage.producer_fingerprint
        ),
        kind=stage.name,
        schema_version=stage.schema_version,
        algorithm_version=stage.algorithm_version,
        dependency_ids=dependency_ids,
        producer_fingerprint=stage.producer_fingerprint,
        content_sha256=content_sha256,
        value=value,
    )
```

Recommended stages and outputs:

| Order | Stage | Primary output |
|---:|---|---|
| 1 | specification | validated effective world specification and seed plan |
| 2 | plates | plate cells, motions, types, boundaries |
| 3 | terrain | elevation, slope, geology, erosion |
| 4 | hydrology | flow, watersheds, rivers, lakes, aquifers |
| 5 | climate | seasonal temperature, precipitation, wind, hazards |
| 6 | ecology | soils, biomes, habitats, species, capacity |
| 7 | resources | deposits, renewable yields, scarcity map |
| 8 | regions | connected named regions and adjacency |
| 9 | travel | route graph and seasonal costs |
| 10 | cultures | peoples, languages, beliefs, material culture |
| 11 | civilizations | governments, initial capitals, territory, inventories |
| 12 | history | complete causal event ledger and snapshots |
| 13 | local maps | coherent 3D maps and event scars for every registered site |
| 14 | opportunities | factual story-facing pressures and candidates |
| 15 | maps/indexes | visual maps, spatial/reference/search indexes |
| 16 | acceptance | cross-domain validation and immutable publication |

## Mathematical and algorithmic specification

This section closes the gap between architectural examples and implementable
algorithms. Production implementations may optimize these algorithms, but must
preserve their declared inputs, invariants, tie-breaking, and canonical outputs.

### Numeric profile and version-stable random generator

Canonical procedural calculations use signed integers. Recommended units are:

| Quantity | Canonical unit |
|---|---|
| normalized scalar | parts per million, `0..1_000_000` |
| elevation/depth | metres |
| temperature | milli-degrees Celsius |
| precipitation | millimetres per season |
| distance | metres |
| population/resources | indivisible integer units |
| probability | parts per million |
| route cost | integer cost units |

Floating point may be used for preview rendering, never as the only canonical
state. Division uses an explicit rounding rule:

```python
PPM = 1_000_000

def div_round_half_up(numerator: int, denominator: int) -> int:
    if denominator <= 0 or numerator < 0:
        raise ValueError("this canonical helper accepts nonnegative values only")
    return (numerator + denominator // 2) // denominator

def mul_ppm(left: int, right: int) -> int:
    return div_round_half_up(left * right, PPM)
```

Do not rely on the host language's random implementation across versions. The
following SplitMix64 stream is the reference generator; all operations are masked
to 64 bits:

```python
MASK64 = (1 << 64) - 1

class SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & MASK64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def below(self, exclusive_upper: int) -> int:
        if exclusive_upper <= 0:
            raise ValueError("upper bound must be positive")
        limit = ((1 << 64) // exclusive_upper) * exclusive_upper
        while True:
            value = self.next_u64()
            if value < limit:
                return value % exclusive_upper

    def chance_ppm(self, probability: int) -> bool:
        if not 0 <= probability <= PPM:
            raise ValueError("probability must be in 0..PPM")
        return self.below(PPM) < probability
```

The SHA-256 domain seed feeds `SplitMix64`; changing RNG algorithm requires an
algorithm-version change and new golden vectors.

### Plate placement and boundary equations

Place candidate plate centers in deterministic shuffled cell order. Accept a
candidate if its squared distance from all accepted centers is at least the
configured spacing squared. Reduce spacing deterministically only if the requested
count cannot be reached. Assign each cell to the minimum tuple
`(distance_squared, plate_id)`.

Each plate has motion vector `(vx, vy)` in signed parts per million. For adjacent
plates A and B, let `n` be the fixed-point unit normal from A's center to B's center
and `r = velocity_B - velocity_A`:

```text
normal_motion = dot(r, n)
tangent_motion = abs(cross(r, n))

normal_motion < -convergence_threshold  -> convergent
normal_motion >  divergence_threshold   -> divergent
otherwise if tangent_motion is large    -> transform
otherwise                               -> passive
```

Continental plates start above oceanic plates. Boundary influence decays linearly
with integer distance `d` over radius `R`:

```text
influence(d, R) = max(0, R - d) / R
convergent uplift = influence × relative convergence × uplift coefficient
divergent rift    = influence × relative divergence  × rift coefficient
transform relief = signed noise × influence × transform coefficient
```

To enforce continent count, threshold the elevation at sea level, label connected
land components using 8-neighbor connectivity, then perform bounded deterministic
adjustments:

- too many components: raise the lowest-cost saddle joining the two closest major
  components, or submerge components below the configured minimum area;
- too few components: lower the minimum-cost ocean channel separating two high
  interior basins;
- stop only when the exact count and minimum-area rules pass;
- fail generation if the bounded adjustment budget is exhausted.

The adjustment ledger records every changed cell and reason; it is part of terrain
provenance.

### Erosion equations

Apply thermal erosion in synchronous passes. For cell `c` and lower neighbor `n`,
material moved is:

```text
excess = elevation[c] - elevation[n] - talus_metres
move(c,n) = max(0, excess × thermal_rate_ppm / PPM)
```

Distribute at most the cell's available movable material among lower neighbors in
canonical neighbor order, using proportional integer allocation plus a stable
remainder pass. Read from the prior pass and write to a separate delta grid.

Hydraulic erosion uses rainfall, flow accumulation, slope, sediment, and capacity:

```text
water[c]       = rainfall[c] + sum(outflow from upstream)
capacity[c]    = water[c] × max(1, slope[c]) × capacity_factor
erode[c]       = min(erodible[c], max(0, capacity[c] - sediment[c]))
deposit[c]     = min(sediment[c], max(0, sediment[c] - capacity[c]))
new_height[c]  = height[c] - erode[c] + deposit[c]
```

Mass validation asserts:

```text
sum(initial elevation material)
= sum(final elevation material) + exported ocean sediment
```

No pass mutates a neighbor that has not yet been evaluated.

### Complete priority-flood hydrology

Priority flood raises enclosed depressions to their lowest spill elevation while
retaining original elevation so lakes can later be reconstructed.

```python
from heapq import heapify, heappop, heappush

CARDINAL = ((0, -1), (-1, 0), (1, 0), (0, 1))

def neighbors4(index: int, width: int, height: int) -> tuple[int, ...]:
    x, y = index % width, index // width
    result = []
    for dx, dy in CARDINAL:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            result.append(ny * width + nx)
    return tuple(result)

def priority_flood(heightmap: tuple[int, ...], width: int, height: int
                   ) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if len(heightmap) != width * height:
        raise ValueError("heightmap shape mismatch")
    filled = list(heightmap)
    parent = [-1] * len(heightmap)
    visited = [False] * len(heightmap)
    heap: list[tuple[int, int]] = []

    boundary = sorted({
        *(x for x in range(width)),
        *((height - 1) * width + x for x in range(width)),
        *(y * width for y in range(height)),
        *(y * width + width - 1 for y in range(height)),
    })
    for index in boundary:
        visited[index] = True
        heap.append((filled[index], index))
    heapify(heap)

    while heap:
        spill_height, current = heappop(heap)
        for neighbor in neighbors4(current, width, height):
            if visited[neighbor]:
                continue
            visited[neighbor] = True
            parent[neighbor] = current
            filled[neighbor] = max(heightmap[neighbor], spill_height)
            heappush(heap, (filled[neighbor], neighbor))
    return tuple(filled), tuple(parent)
```

Flow direction selects the lowest filled neighbor, then the priority-flood parent
when all neighbors are level. Ties use neighbor index. Accumulation processes cells
in descending `(filled_height, index)` order:

```python
def flow_and_accumulation(original: tuple[int, ...], filled: tuple[int, ...],
                          parent: tuple[int, ...], width: int, height: int
                          ) -> tuple[tuple[int, ...], tuple[int, ...]]:
    flow = [-1] * len(filled)
    for cell in range(len(filled)):
        candidates = [(filled[n], n) for n in neighbors4(cell, width, height)]
        if not candidates:
            continue
        best_height, best = min(candidates)
        if best_height < filled[cell]:
            flow[cell] = best
        elif parent[cell] >= 0:
            flow[cell] = parent[cell]

    accumulation = [1] * len(filled)
    for cell in sorted(range(len(filled)), key=lambda i: (filled[i], i), reverse=True):
        target = flow[cell]
        if target >= 0:
            accumulation[target] += accumulation[cell]
    return tuple(flow), tuple(accumulation)
```

A lake is a maximal connected set where `filled > original`. Its surface is the
maximum filled value in the set; its canonical outlet is the minimum
`(filled_height, outside_index, inside_index)` boundary edge. A basin without a
path to ocean is explicitly endorheic. River discharge is:

```text
runoff[cell,season] = precipitation × runoff_coefficient
                    + snowmelt - infiltration - evapotranspiration
discharge[cell,season] = runoff[cell,season]
                       + sum(discharge of upstream cells)
```

All terms are nonnegative integers. A river begins when annual accumulation and at
least one seasonal discharge exceed configured thresholds.

### Wind and moisture transport

Represent wind as one of eight canonical directions plus integer speed. Determine
the large-scale direction from latitude band and season, then perturb it only by a
bounded deterministic pressure field.

For every season, sweep cells in upwind topological order. Where wind cycles are
possible, use a fixed number of Jacobi iterations reading the previous moisture
grid:

```text
source = ocean_evaporation + lake_evaporation + vegetation_recycling
incoming = weighted moisture from upwind neighbors
lift = max(0, elevation[c] - weighted_upwind_elevation)
condensation = incoming × saturation(temp) × lift_factor(lift)
rain = min(incoming + source, base_convective_rain + condensation)
next_moisture = incoming + source - rain
```

Use a fixed lookup table for saturation rather than platform-dependent exponentials.
After the declared iteration count, store precipitation and residual moisture.
Validation checks nonnegative water, bounded atmospheric moisture, expected coastal
moderation, and statistically stronger windward precipitation than corresponding
leeward cells.

### Biome decision table

Classify hard constraints first, then climate bands. Values below are candidate
defaults expressed in canonical units and must be frozen by algorithm version.

| Priority | Condition | Biome |
|---:|---|---|
| 1 | below sea level and depth > 200 m | deep ocean |
| 2 | below sea level | coastal water |
| 3 | permanent ice fraction ≥ 800,000 ppm | glacier |
| 4 | elevation ≥ 3,500 m | alpine peak |
| 5 | elevation ≥ 2,000 m or slope ≥ 600,000 ppm | mountain |
| 6 | saline + waterlogged | marsh |
| 7 | freshwater waterlogged + warm | swamp |
| 8 | mean temperature ≤ −5°C | tundra |
| 9 | precipitation < 200 mm/year | desert |
| 10 | precipitation < 350 mm/year and fertility low | badlands |
| 11 | cold + precipitation ≥ 350 mm/year | taiga |
| 12 | hot + precipitation ≥ 1,500 mm/year | tropical forest |
| 13 | precipitation ≥ 800 mm/year | temperate forest |
| 14 | hot + precipitation ≥ 450 mm/year | savanna |
| 15 | drainage low + precipitation ≥ 600 mm/year | marsh |
| 16 | precipitation ≥ 400 mm/year | grassland |
| 17 | otherwise | shrubland |

Every cell takes the first matching row. A validator proves that every possible
input reaches one row and hard-invalid combinations cannot be selected.

### Ecology and carrying capacity

Net primary productivity uses a limiting-factor model:

```text
temperature_factor = triangular suitability for biome plants
water_factor       = min(1, available_water / water_demand)
soil_factor        = weighted fertility, depth, drainage
NPP                = maximum_NPP × min(temperature_factor,
                                        water_factor,
                                        soil_factor)
```

Human-equivalent carrying capacity per region is:

```text
edible_energy = wild_food + sustainable_harvest + farm_output + net_food_import
required_energy = annual_energy_per_person × reserve_factor
sanitation_limit = fresh_water_capacity × sanitation_technology
shelter_limit = buildable_land × material_and_labor_factor
capacity = min(edible_energy / required_energy,
               sanitation_limit,
               shelter_limit)
```

Species occupancy requires habitat suitability, a connected migration path, and a
viable population. Predator population is bounded by prey energy. Harvest cannot
exceed renewable yield indefinitely; overharvest reduces next year's population
and may emit extinction events.

### Region segmentation

Create atomic regions by seeded watershed/biome flood fill:

1. identify deterministic seeds at watershed outlets, major islands, and cells
   farther than the minimum radius from an existing seed;
2. push each seed into a priority queue;
3. grow by minimum tuple `(cumulative travel cost, seed_id, cell_index)`;
4. prevent crossing ocean or impassable barriers unless the region type permits it;
5. split disconnected results;
6. merge undersized regions with the neighboring region having minimum boundary
   cost, breaking ties by region ID;
7. record symmetric adjacency and shared boundary length.

This is deterministic multi-source Dijkstra, not a random flood fill.

### Route search, capacity, and trade

Use A* with stable heap tuples `(f_cost, g_cost, cell_index)` and an admissible
integer heuristic. Movement cost includes distance, slope, biome, river crossing,
season, hostility, and infrastructure. Cache keys include all cost-profile hashes.

Route capacity is the minimum edge capacity along its course. Annual shipment is:

```text
tradable_surplus = max(0, source_stock - source_reserve)
demand           = max(0, target_reserve - target_stock)
shipment         = min(tradable_surplus, demand, route_remaining_capacity)
delivered        = shipment - transport_loss
```

Price is an integer index, not floating currency:

```text
scarcity_ppm = clamp(target_reserve × PPM / max(1, target_stock), 250k, 4M)
price = base_value × scarcity_ppm / PPM
      + transport_cost + risk_premium + tariff
```

Transfer source inventory, destination inventory, payment, loss, and capacity in
one event. The combined goods ledger must balance.

### Population, migration, disease, succession, and war

Birth and natural-death expectations use integer demographic cohorts. Stochastic
rounding consumes a domain-specific RNG:

```python
def stochastic_count(population: int, rate_ppm: int, rng: SplitMix64) -> int:
    scaled = population * rate_ppm
    whole, remainder = divmod(scaled, PPM)
    return whole + int(rng.below(PPM) < remainder)
```

Migration pressure combines food deficit, danger, persecution, kinship, wage/trade
opportunity, and route feasibility. Every migrant is removed from an origin cohort
and added to a destination cohort in the same event.

Disease uses a deterministic compartment model per settlement:

```text
new_exposed  = contacts × susceptible × infectious / population
new_infected = exposed × incubation_rate
new_recovered= infected × recovery_rate
new_dead     = infected × fatality_rate × care_modifier
```

Clamp transitions to available compartment counts and apply in a synchronous
delta. Travel moves explicit infected cohorts and can seed another site.

Succession candidates are filtered by government law, kinship/office, living
status, age, location, and disqualification. Rank by an explicit tuple of legal
priority, support, legitimacy, deterministic lot, and stable ID. A succession
event removes the old office-holder and assigns exactly one successor or records an
interregnum. Disputed close rankings create factions; they do not silently choose
two rulers.

War requires a casus belli or policy motive, reachable opponent, supply capacity,
political decision, and expected-utility threshold. Army size is bounded by
available eligible population, equipment, treasury, and food. Monthly supply:

```text
required = soldiers × ration_per_soldier
delivered = min(required, stock, route_capacity)
readiness = delivered / required × equipment × morale
attrition = climate_hazard + shortage + disease + combat
```

Combat uses declared force, terrain, fortification, readiness, command, and bounded
random draw. Losses are subtracted from armies and their population cohorts.
Occupation and territorial transfer require explicit events and valid connected
geometry.

### Local caves, fluids, heat, and support

Caves are connected carved volumes. Seed chambers only in soluble/fractured strata,
connect them with deterministic 3D A*, and either connect each cave system to an
entrance/aquifer or mark it sealed. Remove isolated single-voxel noise.

Liquids use integer volume `0..7` per tile and synchronous deltas. For each tile,
consider downward flow first, then horizontal flow in canonical order:

```text
downward_transfer = min(source_volume, 7 - below_volume)
head_difference = source_surface_height - neighbor_surface_height
horizontal_transfer = min(remaining, max(0, head_difference / 2),
                          7 - neighbor_volume)
```

The sum of water changes only through declared sources, sinks, evaporation, or map
boundaries. Magma is a distinct liquid and contact reactions are explicit.

Heat diffusion uses fixed-point synchronous updates:

```text
delta[c] = conductivity × sum(temp[n] - temp[c]) / neighbor_count
new_temp[c] = temp[c] + delta[c] + sources[c] - sinks[c]
```

Structural support forms a graph from solid/constructed tiles to bedrock anchors.
A tile is supported when a path exists through load-bearing connections and total
load does not exceed material capacity. Mining removes edges; unsupported connected
components collapse through explicit local events. Empty neighboring tiles never
provide support.

## Runnable miniature reference generator

The following standard-library program is intentionally small but complete. It
demonstrates version-stable seeds, fixed-point-ish integer terrain, an exact
one-continent constraint, priority-flood hydrology, flow accumulation, deterministic
climate/biomes, settlements, causal population history, validation, and canonical
JSON output. It is a reference vertical slice, not the final fidelity target.

```python
# generation_reference.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from heapq import heapify, heappop, heappush
import json
import math

MASK64 = (1 << 64) - 1
PPM = 1_000_000
CARDINAL = ((0, -1), (-1, 0), (1, 0), (0, 1))

def seed64(master: int, domain: str, *parts: object) -> int:
    text = "\x1f".join([str(master), domain, *(str(p) for p in parts)])
    return int.from_bytes(sha256(text.encode()).digest()[:8], "big")

class Rng:
    def __init__(self, seed: int): self.state = seed & MASK64
    def u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64
    def below(self, n: int) -> int:
        if n <= 0: raise ValueError("positive bound required")
        limit = ((1 << 64) // n) * n
        while True:
            value = self.u64()
            if value < limit: return value % n

@dataclass(frozen=True)
class Spec:
    seed: int = 42
    width: int = 40
    height: int = 24
    sea_level_m: int = 0
    years: int = 50

@dataclass(frozen=True)
class Event:
    id: str
    year: int
    kind: str
    causes: tuple[str, ...]
    before: int
    after: int

def neighbors(index: int, spec: Spec) -> tuple[int, ...]:
    x, y = index % spec.width, index // spec.width
    found = []
    for dx, dy in CARDINAL:
        nx, ny = x + dx, y + dy
        if 0 <= nx < spec.width and 0 <= ny < spec.height:
            found.append(ny * spec.width + nx)
    return tuple(found)

def terrain(spec: Spec) -> tuple[int, ...]:
    """Radial continent plus deterministic multi-frequency integer texture."""
    cx2, cy2 = spec.width - 1, spec.height - 1  # doubled center
    radius2 = min(spec.width, spec.height) - 4  # doubled radius
    result = []
    for y in range(spec.height):
        for x in range(spec.width):
            dx2, dy2 = 2 * x - cx2, 2 * y - cy2
            radial = radius2 * radius2 - dx2 * dx2 - dy2 * dy2
            texture = (seed64(spec.seed, "terrain", x // 3, y // 3) % 401) - 200
            detail = (seed64(spec.seed, "detail", x, y) % 81) - 40
            result.append(radial * 3 + texture + detail)
    # Boundary ocean guarantees one bounded continental candidate.
    for x in range(spec.width):
        result[x] = result[(spec.height - 1) * spec.width + x] = -10_000
    for y in range(spec.height):
        result[y * spec.width] = result[y * spec.width + spec.width - 1] = -10_000
    return tuple(result)

def retain_largest_land(heightmap: tuple[int, ...], spec: Spec) -> tuple[int, ...]:
    land = {i for i, value in enumerate(heightmap) if value > spec.sea_level_m}
    components = []
    while land:
        start = min(land); stack = [start]; component = set(); land.remove(start)
        while stack:
            current = stack.pop(); component.add(current)
            for nxt in neighbors(current, spec):
                if nxt in land: land.remove(nxt); stack.append(nxt)
        components.append(component)
    if not components: raise ValueError("no land generated")
    keep = min(components, key=lambda c: (-len(c), min(c)))
    return tuple(v if i in keep or v <= spec.sea_level_m else spec.sea_level_m
                 for i, v in enumerate(heightmap))

def priority_flood(values: tuple[int, ...], spec: Spec) -> tuple[tuple[int, ...], tuple[int, ...]]:
    filled, parent = list(values), [-1] * len(values)
    seen, heap = [False] * len(values), []
    boundary = sorted({*(range(spec.width)),
        *((spec.height - 1) * spec.width + x for x in range(spec.width)),
        *(y * spec.width for y in range(spec.height)),
        *(y * spec.width + spec.width - 1 for y in range(spec.height))})
    for i in boundary: seen[i] = True; heap.append((filled[i], i))
    heapify(heap)
    while heap:
        level, current = heappop(heap)
        for nxt in neighbors(current, spec):
            if seen[nxt]: continue
            seen[nxt], parent[nxt] = True, current
            filled[nxt] = max(values[nxt], level)
            heappush(heap, (filled[nxt], nxt))
    return tuple(filled), tuple(parent)

def drainage(values: tuple[int, ...], filled: tuple[int, ...], parent: tuple[int, ...],
             spec: Spec) -> tuple[tuple[int, ...], tuple[int, ...]]:
    flow = [-1] * len(values)
    for i in range(len(values)):
        options = sorted((filled[n], n) for n in neighbors(i, spec))
        if options and options[0][0] < filled[i]: flow[i] = options[0][1]
        elif parent[i] >= 0: flow[i] = parent[i]
    accumulation = [1] * len(values)
    for i in sorted(range(len(values)), key=lambda n: (filled[n], n), reverse=True):
        if flow[i] >= 0: accumulation[flow[i]] += accumulation[i]
    return tuple(flow), tuple(accumulation)

def climate_biomes(values: tuple[int, ...], accumulation: tuple[int, ...],
                   spec: Spec) -> tuple[dict[str, object], ...]:
    cells = []
    for i, elevation in enumerate(values):
        x, y = i % spec.width, i // spec.width
        latitude_ppm = abs(2 * y - (spec.height - 1)) * PPM // max(1, spec.height - 1)
        temp_mc = 28_000 - latitude_ppm * 38_000 // PPM - max(0, elevation) * 6
        coast = any(values[n] <= spec.sea_level_m for n in neighbors(i, spec))
        rain_mm = 250 + (500 if coast else 0) + int(seed64(spec.seed, "rain", i) % 700)
        river = accumulation[i] >= 25 and elevation > spec.sea_level_m
        if elevation <= spec.sea_level_m: biome = "ocean"
        elif elevation > 900: biome = "mountain"
        elif temp_mc <= -5_000: biome = "tundra"
        elif rain_mm < 300: biome = "desert"
        elif rain_mm >= 900: biome = "forest"
        else: biome = "grassland"
        cells.append({"i": i, "x": x, "y": y, "elevation_m": elevation,
                      "temperature_mc": temp_mc, "rain_mm": rain_mm,
                      "river": river, "biome": biome})
    return tuple(cells)

def settlements(cells: tuple[dict[str, object], ...], spec: Spec) -> tuple[int, ...]:
    candidates = []
    for cell in cells:
        if cell["biome"] in ("ocean", "mountain", "tundra"): continue
        score = int(cell["rain_mm"]) + (800 if cell["river"] else 0)
        score -= abs(int(cell["temperature_mc"]) - 15_000) // 20
        candidates.append((-score, int(cell["i"])))
    selected = []
    for _, index in sorted(candidates):
        x, y = index % spec.width, index // spec.width
        if all(abs(x - s % spec.width) + abs(y - s // spec.width) >= 8 for s in selected):
            selected.append(index)
        if len(selected) == 3: break
    if not selected: raise ValueError("no suitable settlement")
    return tuple(sorted(selected))

def history(site_indices: tuple[int, ...], spec: Spec) -> tuple[Event, ...]:
    population = 100 * len(site_indices)
    events = []
    previous = ""
    for year in range(spec.years):
        rng = Rng(seed64(spec.seed, "history", year))
        capacity = 450 * len(site_indices)
        births = population * 35 // 1000
        deaths = population * (18 + rng.below(8)) // 1000
        growth = min(births - deaths, max(0, capacity - population))
        before, population = population, max(0, population + growth)
        event_id = f"event_{sha256(f'{spec.seed}:{year}'.encode()).hexdigest()[:32]}"
        events.append(Event(event_id, year, "population_change",
                            (previous,) if previous else (), before, population))
        previous = event_id
    return tuple(events)

def validate(world: dict[str, object], spec: Spec) -> None:
    values = world["elevation_m"]; flow = world["flow"]; events = world["events"]
    assert isinstance(values, tuple) and len(values) == spec.width * spec.height
    land = {i for i, v in enumerate(values) if v > spec.sea_level_m}
    seen, stack = set(), [min(land)]
    while stack:
        i = stack.pop()
        if i in seen: continue
        seen.add(i); stack.extend(n for n in neighbors(i, spec) if n in land)
    assert seen == land, "land must be exactly one continent"
    assert isinstance(flow, tuple)
    for start in range(len(flow)):
        cursor, visited = start, set()
        while flow[cursor] >= 0:
            assert cursor not in visited, "drainage cycle"
            visited.add(cursor); cursor = flow[cursor]
    assert isinstance(events, tuple)
    state = events[0].before if events else 0
    known = set()
    for event in events:
        assert event.before == state and all(c in known for c in event.causes)
        state = event.after; known.add(event.id)

def generate(spec: Spec) -> dict[str, object]:
    raw = retain_largest_land(terrain(spec), spec)
    filled, parent = priority_flood(raw, spec)
    flow, accumulation = drainage(raw, filled, parent, spec)
    cells = climate_biomes(raw, accumulation, spec)
    sites = settlements(cells, spec)
    events = history(sites, spec)
    world = {"spec": spec, "elevation_m": raw, "filled_m": filled,
             "flow": flow, "accumulation": accumulation, "cells": cells,
             "site_indices": sites, "events": events}
    validate(world, spec)
    return world

def canonical(value: object) -> bytes:
    def convert(item: object) -> object:
        if hasattr(item, "__dataclass_fields__"): return convert(asdict(item))
        if isinstance(item, dict): return {k: convert(v) for k, v in sorted(item.items())}
        if isinstance(item, (tuple, list)): return [convert(v) for v in item]
        return item
    return json.dumps(convert(value), sort_keys=True, separators=(",", ":")).encode()

if __name__ == "__main__":
    generated = canonical(generate(Spec()))
    print(sha256(generated).hexdigest())
    print(generated.decode())
```

Golden tests must pin the output hash of this reference for selected seeds and
specifications. Production code should use chunked arrays and richer algorithms,
but it must retain the same discipline: explicit seeds, integer boundaries,
deterministic ties, complete state transitions, and validation before publication.

### Reference conformance vector

With Python 3.9+ and the program exactly as printed above:

```text
Spec(seed=42, width=40, height=24, sea_level_m=0, years=50)
canonical byte length: 130169
SHA-256: 5750580acac80e862ab0aa84de9d2225b3b781c0ede7f17cd4df47f503089dc2
selected site indices: 330, 629, 822
history event count: 50
```

This vector tests the embedded miniature kernel only. A production
`worldgen-1` implementation must publish separate golden vectors for each domain,
but all such vectors use the canonical rules and artifact envelopes defined here.

## Complete acceptance and test matrix

### Specification and seed tests

- every minimum, maximum, and just-outside value;
- invalid combinations and infeasible resource estimates;
- configuration order/path independence;
- SplitMix64 golden outputs, unbiased `below`, and domain-seed separation;
- changing one parameter invalidates exactly its dependency closure.

### Physical-domain tests

- exact continent count, minimum component area, and bounded adjustment ledger;
- plate coverage, symmetric boundaries, and motion classification;
- erosion material conservation and synchronous-pass independence;
- priority-flood basins against hand-calculated fixtures;
- river termination, tributary acyclicity, lake outlets, seasonal water balance;
- temperature lapse, coastal moderation, windward/leeward precipitation;
- total biome classification and invalid-combination rejection;
- geology/deposit compatibility, soil coverage, food-web energy bounds;
- region connectivity/adjacency and route feasibility/capacity.

### Social and history tests

- site suitability, minimum separation, ownership, containment, and capacity;
- population cohort, migrant, army, inventory, currency, and deposit conservation;
- recipe input/output balance, spoilage, shortage, trade, and route capacity;
- disease compartment bounds and travel propagation;
- legal succession, disputed succession, interregnum, reform, schism, and extinction;
- war motive, reachability, supply, losses, peace, occupation, and territory changes;
- magic prerequisite/cost/effect enforcement and prohibited-effect rejection;
- every event cause precedes it and every state change applies exactly once;
- snapshot replay equals genesis replay at every snapshot boundary.

### Local, map, and story-facing tests

- local strata, river/coast, route, building, material, ownership, and event scars
  agree with macro facts;
- caves are connected or explicitly sealed; liquids/heat conserve declared units;
- support removal produces deterministic collapse components;
- every map feature and raster label points to authoritative source IDs;
- indexes rebuild byte-identically and contain every incoming/outgoing reference;
- opportunities introduce no facts and all participants/routes are feasible;
- enrichment adds only contained minor entities and never changes major history.

### Reliability and security tests

- one worker versus many, repeated runs, supported platforms, output directories,
  and iteration-order perturbation produce identical domain bytes;
- process termination is injected before/after every flush, rename, directory sync,
  envelope commit, history batch, and snapshot;
- resume equals uninterrupted output and rejects altered dependencies;
- integer overflow, invalid dimensions, malformed registries, duplicate IDs, deep
  JSON, path escape, corrupt chunks, and decompression exhaustion fail safely;
- no procedural stage performs network access or invokes a language model;
- full-data inventory proves no unused procedural record was discarded.

### Acceptance algorithm

```python
def accept_world(envelopes: tuple[ArtifactEnvelope, ...],
                 reports: tuple[ValidationReport, ...]) -> None:
    by_kind = {envelope.kind: envelope for envelope in envelopes}
    required = set(ArtifactKind.__args__)  # type: ignore[attr-defined]
    missing = sorted(required - set(by_kind))
    if missing:
        raise ValueError(("WG-INDEX-001", "missing required artifacts", missing))
    if len(by_kind) != len(envelopes):
        raise ValueError(("WG-INDEX-001", "duplicate artifact kind"))
    known_ids = {envelope.artifact_id for envelope in envelopes}
    for envelope in envelopes:
        if not set(envelope.dependency_ids) <= known_ids:
            raise ValueError(("WG-INDEX-001", envelope.artifact_id, "broken dependency"))
        if len(envelope.content_sha256) != 64:
            raise ValueError(("WG-PERSIST-001", envelope.artifact_id, "invalid hash"))
    issues = [issue for report in reports for issue in report.errors]
    if issues:
        raise ValueError(("world validation failed", issues))
```

Final acceptance additionally recomputes every content hash, proves the dependency
graph acyclic, replays history, rebuilds indexes, validates required local maps,
and compares the inventory with the effective specification. Only then is the
immutable world eligible for packaging or narrative derivation.

## Prototype provenance retained before deletion

The generation design was informed by two MIT-licensed prototypes:

| Prototype | Upstream identity | Reviewed ideas retained |
|---|---|---|
| Dwarf Fortress Simulation | `kevshakes/dwarf-fortress-simulation`, commit `d1c3c40c13e258d1539ef5d5bdb56cfc093ddec2`, MIT, copyright 2025 Dwarf Fortress Simulation | 3D tiles, biomes, deposits, temperature, needs, skills, relationships, stockpiles, production recipes, pathfinding, local physics boundaries, saveable simulation state |
| DF Style Worldgen | `Dozed12/df-style-worldgen`, commit `937455d54f4b02df9c4b10ae6418f4c932fd97bf`, MIT, copyright 2016 Dozed | continental height fields, polar effects, tectonic uplift, erosion, rainfall/drainage views, rivers, prosperity, data-driven peoples/governments, flags, settlement suitability, population growth, expansion, diplomacy and armies |

The algorithms and code in this document are a new specification rather than a
verbatim copy. If substantial source code or data is later copied from either
prototype, retain its full MIT notice in the distributed source and third-party
notices. Names, race tables, government prose, flag masks, and naming grammars are
not required canonical inputs; equivalent original registries should be authored
and versioned for this project.

## What to avoid

- using noise as a substitute for hydrology, geology, economy, or history;
- applying biome `if` statements that overlap and silently overwrite each other;
- choosing river steps without bounds checks, basin handling, or deterministic
  tie-breaking;
- using mutable class-level lists for civilization sites or populations;
- using global RNG state or process-dependent `hash()` to place resources;
- emitting history descriptions without participants, causes, or state changes;
- duplicating population when founding settlements or armies;
- generating trade without inventory and feasible routes;
- permitting vertical pathfinding through arbitrary empty cells;
- storing out-of-bounds access as a fabricated empty tile;
- silently reducing world size or fidelity when resources are insufficient;
- letting a language model define authoritative geography or revise history;
- discarding simulation data because the selected narrative did not use it.

## Minimum useful first implementation

A disciplined first vertical slice should generate:

1. one configurable continent on a small fixed-point grid;
2. plates, elevation, erosion, coast, slope, and geology;
3. priority-flood hydrology with watersheds, rivers, and lakes;
4. four-season temperature and orographic rainfall;
5. soils, biomes, resources, regions, and route costs;
6. two or more peoples, governments, capitals, settlements, and stockpiles;
7. fifty deterministic history years with population, production, trade, one
   succession path, and conflict/peace state transitions;
8. a local 3D map for every registered site, each aligned with macro geology and roads;
9. a complete ledger, snapshots, validation report, and canonical hashes;
10. opportunity extraction without narrative prose.

Only after this slice passes invariant, replay, worker-independence, resume, and
cross-platform tests should the design expand to more species, religions, weather,
politics, production, local physics, or longer history.

## Definition of done

World generation is complete when:

- the same specification and algorithm versions reproduce identical procedural
  bytes across supported platforms and worker counts;
- physical, ecological, spatial, economic, civilization, history, and local-map
  validators all pass;
- every historical fact can be traced to prior state and explicit changes;
- local detail agrees with macro geography, resources, routes, ownership, and
  history;
- complete procedural data, event ledger, maps, indexes, provenance, and validation
  evidence are retained;
- story systems can select opportunities and facts without inventing or mutating
  authoritative world state;
- generation can resume safely at domain boundaries and produces the same result
  as an uninterrupted run;
- a failed mandatory domain aborts publication instead of falling back to a hidden
  simpler world.
