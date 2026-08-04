"""Worldgen data models — immutable dataclasses + deterministic RNG.

All generation derives from a single seed. The RNG is a simple
linear congruential generator that produces reproducible sequences
across platforms and Python versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── deterministic RNG ─────────────────────────────────────────────────


class WorldRNG:
    """Simple deterministic LCG PRNG. Same seed = same sequence everywhere.

    Uses glibc/ANSI C parameters: multiplier 1103515245, increment 12345,
    modulus 2^31. This is the same RNG used by rand() on most systems.

    Usage:
        rng = WorldRNG(42)
        elevation = rng.uniform(-1.0, 1.0)  # deterministic
        idx = rng.randint(0, 10)             # deterministic
    """

    _MULTIPLIER: int = 1103515245
    _INCREMENT: int = 12345
    _MODULUS: int = 2**31

    def __init__(self, seed: int) -> None:
        self._state: int = (seed ^ self._MULTIPLIER) & 0x7FFFFFFF

    def _next(self) -> int:
        self._state = (self._state * self._MULTIPLIER + self._INCREMENT) % self._MODULUS
        return self._state

    def uniform(self, lo: float = 0.0, hi: float = 1.0) -> float:
        """Return a float in [lo, hi)."""
        return lo + (hi - lo) * (self._next() / self._MODULUS)

    def randint(self, lo: int, hi: int) -> int:
        """Return an integer in [lo, hi] (inclusive)."""
        return lo + self._next() % (hi - lo + 1)

    def choice(self, items: list[str]) -> str:
        """Return a random element from a list."""
        return items[self.randint(0, len(items) - 1)]

    def choose_weighted(self, weighted: list[tuple[str, float]]) -> str:
        """Return a weighted random choice."""
        total = sum(w for _, w in weighted)
        r = self.uniform(0, total)
        cumulative = 0.0
        for item, weight in weighted:
            cumulative += weight
            if r < cumulative:
                return item
        return weighted[-1][0]

    def sample(self, items: list[str], k: int) -> list[str]:
        """Return k random elements without replacement."""
        # Fisher-Yates partial shuffle
        pool = items[:]
        result: list[str] = []
        for i in range(min(k, len(pool))):
            j = self.randint(i, len(pool) - 1)
            pool[i], pool[j] = pool[j], pool[i]
            result.append(pool[i])
        return result

    def noise_2d(self, x: int, y: int, scale: float = 1.0) -> float:
        """Deterministic 2D value noise (hash-based, not Perlin).

        Returns a value in [-1.0, 1.0] that varies smoothly with x, y.
        This is a simple hash-based noise — good enough for worldgen.
        """
        # Use a hash function seeded by state + coordinates
        hx = (x * 374761393 + self._state * 3266489917) & 0x7FFFFFFF
        hy = (y * 668265263 + self._state * 2246822519) & 0x7FFFFFFF
        h = ((hx * 2654435761) ^ (hy * 3141592653)) & 0x7FFFFFFF
        return 2.0 * (h / 0x7FFFFFFF) - 1.0

    def noise_2d_smooth(self, x: int, y: int, scale: float = 1.0) -> float:
        """Smooth 2D noise using bilinear interpolation of 4 hash samples."""
        sx = x / scale
        sy = y / scale
        ix, iy = int(sx), int(sy)
        fx, fy = sx - ix, sy - iy

        # Smoothstep interpolation
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)

        n00 = self.noise_2d(ix, iy, scale)
        n10 = self.noise_2d(ix + 1, iy, scale)
        n01 = self.noise_2d(ix, iy + 1, scale)
        n11 = self.noise_2d(ix + 1, iy + 1, scale)

        nx0 = n00 + (n10 - n00) * fx
        nx1 = n01 + (n11 - n01) * fx
        return nx0 + (nx1 - nx0) * fy


# ── enums ──────────────────────────────────────────────────────────────


class Biome(str, Enum):
    TUNDRA = "tundra"
    TAIGA = "taiga"
    TEMPERATE_FOREST = "temperate_forest"
    TEMPERATE_GRASSLAND = "temperate_grassland"
    DESERT = "desert"
    SAVANNA = "savanna"
    TROPICAL_FOREST = "tropical_forest"
    WETLAND = "wetland"
    MOUNTAIN = "mountain"
    COASTAL = "coastal"
    RIVER_VALLEY = "river_valley"
    HIGHLAND = "highland"


class Elevation(str, Enum):
    DEEP = "deep"
    LOWLAND = "lowland"
    HILLS = "hills"
    HIGHLAND = "highland"
    MOUNTAIN = "mountain"
    PEAK = "peak"


class Climate(str, Enum):
    ARCTIC = "arctic"
    COLD_DRY = "cold_dry"
    COLD_WET = "cold_wet"
    TEMPERATE_DRY = "temperate_dry"
    TEMPERATE_WET = "temperate_wet"
    WARM_DRY = "warm_dry"
    WARM_WET = "warm_wet"
    HOT_DRY = "hot_dry"
    HOT_WET = "hot_wet"


class SiteType(str, Enum):
    SETTLEMENT = "settlement"
    CAPITAL = "capital"
    FORTRESS = "fortress"
    TEMPLE = "temple"
    RUIN = "ruin"
    MINE = "mine"
    PORT = "port"
    CROSSROADS = "crossroads"


# ── dataclasses ────────────────────────────────────────────────────────


@dataclass
class GridCell:
    """A single cell in the world grid."""

    elevation: float = 0.0       # -1.0 (deep ocean) to 1.0 (peak)
    temperature: float = 0.0     # -1.0 (arctic) to 1.0 (tropical)
    precipitation: float = 0.0   # 0.0 (arid) to 1.0 (wet)
    drainage: float = 0.0        # accumulated water flow
    biome: str = ""
    region_id: str = ""
    is_coastal: bool = False
    is_river: bool = False


@dataclass
class Region:
    """A contiguous geographic area."""

    id: str = ""
    name: str = ""
    biome: str = ""
    elevation: str = ""
    climate: str = ""
    prosperity: float = 0.0
    neighbors: list[str] = field(default_factory=list)
    sites: list[str] = field(default_factory=list)
    center_x: int = 0
    center_y: int = 0


@dataclass
class Site:
    """A location within a region (settlement, fortress, etc.)."""

    id: str = ""
    region_id: str = ""
    site_type: str = ""
    civilization_id: str = ""
    population: int = 0
    name: str = ""
    x: int = 0
    y: int = 0


@dataclass
class Civilization:
    """A race/government entity controlling regions."""

    id: str = ""
    name: str = ""
    race: str = ""
    government: str = ""
    controlled_regions: list[str] = field(default_factory=list)
    capital_site: str = ""
    culture: str = ""
    population: int = 0


@dataclass
class HistoryEvent:
    """A single event in the world's simulated history."""

    year: int = 0
    event: str = ""
    participants: list[str] = field(default_factory=list)
    location: str = ""


@dataclass
class WorldSnapshot:
    """Complete procedural world — fed into WorldBuilder."""

    schema_version: int = 1
    seed: int = 0
    dimensions: dict[str, int] = field(default_factory=lambda: {"width": 64, "height": 64})
    regions: list[Region] = field(default_factory=list)
    sites: list[Site] = field(default_factory=list)
    civilizations: list[Civilization] = field(default_factory=list)
    history: list[HistoryEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict matching world_snapshot.schema.json."""
        return {
            "schema_version": self.schema_version,
            "seed": self.seed,
            "dimensions": dict(self.dimensions),
            "regions": [
                {
                    "id": r.id,
                    "name": r.name,
                    "biome": r.biome,
                    "elevation": r.elevation,
                    "climate": r.climate,
                    "prosperity": round(r.prosperity, 3),
                    "neighbors": list(r.neighbors),
                    "sites": list(r.sites),
                }
                for r in self.regions
            ],
            "sites": [
                {
                    "id": s.id,
                    "region_id": s.region_id,
                    "type": s.site_type,
                    "civilization_id": s.civilization_id or "",
                    "population": s.population,
                    "name": s.name,
                }
                for s in self.sites
            ],
            "civilizations": [
                {
                    "id": c.id,
                    "name": c.name,
                    "race": c.race,
                    "government": c.government,
                    "controlled_regions": list(c.controlled_regions),
                    "capital_site": c.capital_site,
                    "culture": c.culture,
                    "population": c.population,
                }
                for c in self.civilizations
            ],
            "history": [
                {
                    "year": h.year,
                    "event": h.event,
                    "participants": list(h.participants),
                    "location": h.location or "",
                }
                for h in self.history
            ],
        }
