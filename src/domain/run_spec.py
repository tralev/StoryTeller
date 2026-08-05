"""Immutable, validated generation specification and deterministic seeds."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields
from typing import Any

_SEED_SEPARATOR = "\x1f"


def derive_seed(master_seed: int, domain: str, *parts: object) -> int:
    """Derive a stable unsigned 64-bit seed for one decision domain."""
    if not domain or domain.strip() != domain:
        raise ValueError("seed domain must be a non-empty canonical string")
    values = (str(master_seed), domain, *(str(part) for part in parts))
    payload = _SEED_SEPARATOR.join(values).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


@dataclass(frozen=True)
class SeedPlan:
    """Versioned domain-seed plan recorded with generated artifacts."""

    master_seed: int
    version: str = "storyteller.seed.sha256.v1"

    def for_domain(self, domain: str, *parts: object) -> int:
        if self.version != "storyteller.seed.sha256.v1":
            raise ValueError(f"unsupported seed-plan version: {self.version}")
        return derive_seed(self.master_seed, domain, *parts)


@dataclass(frozen=True)
class WorldSpec:
    """Complete worldgen-1 configuration, with no unresolved presets."""

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

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not 32 <= self.width <= 8192 or not 32 <= self.height <= 8192:
            raise ValueError("world dimensions must each be within 32..8192")
        if self.continent_count < 1:
            raise ValueError("at least one continent is required")
        if not self.continent_count <= self.plate_count <= 256:
            raise ValueError("plate count must cover continents and be at most 256")
        if self.minimum_continent_cells < 1:
            raise ValueError("minimum continent area must be positive")
        if not 50_000 <= self.sea_level_ppm <= 950_000:
            raise ValueError("sea level must be within 50,000..950,000 ppm")
        if self.history_years < 0 or self.civilization_count < 1:
            raise ValueError("history must be nonnegative and civilizations positive")
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
        if not 32 <= self.local_site_width <= 1024:
            raise ValueError("local site width out of range")
        if not 32 <= self.local_site_height <= 1024:
            raise ValueError("local site height out of range")
        if not 4 <= self.local_z_levels <= 256:
            raise ValueError("local z-level count out of range")
        if self.local_cell_millimetres < 1:
            raise ValueError("local-cell scale must be positive")

    def estimated_working_set_bytes(self) -> int:
        """Conservative Phase 1 preflight estimate for canonical integer grids."""
        world_cells = self.width * self.height
        local_cells = (
            self.local_site_width * self.local_site_height * self.local_z_levels
        )
        return world_cells * 8 * 24 + local_cells * 8

    def preflight(self, *, max_ram_bytes: int) -> None:
        if max_ram_bytes < 1:
            raise ValueError("RAM budget must be positive")
        required = self.estimated_working_set_bytes()
        if required > max_ram_bytes:
            raise ValueError(
                f"world specification requires approximately {required} bytes, "
                f"exceeding RAM budget {max_ram_bytes}"
            )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WorldSpec":
        known = {item.name for item in fields(cls)}
        unknown = set(value) - known
        if unknown:
            raise ValueError("unknown world fields: " + ", ".join(sorted(unknown)))
        return cls(**value)


@dataclass(frozen=True)
class RunSpec:
    """Canonical, immutable input to one generation run."""

    seed: int = 0
    title: str = "Untitled World"
    tone: str = "mature_dark_fantasy"
    temperature: float = 0.7
    world: WorldSpec = field(default_factory=WorldSpec)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be within 0.0..2.0")

    @property
    def seeds(self) -> SeedPlan:
        return SeedPlan(self.seed)

    def derive_seed(self, domain: str, *parts: object) -> int:
        return self.seeds.for_domain(domain, *parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed, "title": self.title, "tone": self.tone,
            "temperature": self.temperature, "world": self.world.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunSpec":
        known = {"seed", "title", "tone", "temperature", "world"}
        unknown = set(value) - known
        if unknown:
            raise ValueError("unknown run fields: " + ", ".join(sorted(unknown)))
        data = dict(value)
        world = data.get("world", {})
        if not isinstance(world, dict):
            raise ValueError("world must be a mapping")
        data["world"] = WorldSpec.from_dict(world)
        return cls(**data)
