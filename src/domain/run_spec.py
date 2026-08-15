"""Immutable, validated generation specification and deterministic seeds."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field, fields
from typing import Any

_SEED_SEPARATOR = "\x1f"
SEED_PLAN_VERSION = "storyteller.seed.sha256.v1"

# Frozen worldgen-1 scalar field rules. Cross-field rules remain explicit in
# WorldSpec.validate() and are named here so the conformance profile can prove
# the complete validation contract is represented.
WORLD_SPEC_FIELD_RULES: dict[str, dict[str, int]] = {
    "width": {"minimum": 32, "maximum": 8192},
    "height": {"minimum": 32, "maximum": 8192},
    "continent_count": {"minimum": 1},
    "metres_per_world_cell": {"minimum": 250, "maximum": 100_000},
    "plate_count": {"minimum": 1, "maximum": 256},
    "minimum_continent_cells": {"minimum": 1},
    "history_years": {"minimum": 0},
    "history_ticks_per_year": {"const": 12},
    "civilization_count": {"minimum": 1},
    "sea_level_ppm": {"minimum": 50_000, "maximum": 950_000},
    "axial_tilt_millidegrees": {"minimum": 0, "maximum": 90_000},
    "erosion_passes": {"minimum": 0, "maximum": 512},
    "climate_relaxation_passes": {"minimum": 8, "maximum": 512},
    "snapshot_interval_years": {"const": 10},
    "local_site_width": {"minimum": 32, "maximum": 1024},
    "local_site_height": {"minimum": 32, "maximum": 1024},
    "local_z_levels": {"minimum": 4, "maximum": 256},
    "local_cell_millimetres": {"minimum": 1},
}

WORLD_SPEC_CROSS_FIELD_RULES = {
    "plate_count_gte_continent_count": "plate_count >= continent_count",
}

WORLD_BUDGET_ALGORITHM_VERSION = "world-budget-v1"


@dataclass(frozen=True)
class WorldBudgetEstimate:
    algorithm_version: str
    site_count: int
    world_cells: int
    local_cells_per_site: int
    total_local_cells: int
    peak_ram_bytes: int
    disk_bytes: int
    time_milliseconds: int


@dataclass(frozen=True)
class WorldBudgetDiagnostic:
    code: str
    resource: str
    required: int
    budget: int
    site_count: int


class WorldBudgetError(ValueError):
    def __init__(self, diagnostic: WorldBudgetDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            f"{diagnostic.code}: resource={diagnostic.resource}; "
            f"required={diagnostic.required}; budget={diagnostic.budget}; "
            f"site_count={diagnostic.site_count}"
        )


def derive_seed(
    master_seed: int,
    domain: str,
    *parts: object,
    version: str = SEED_PLAN_VERSION,
) -> int:
    """Derive a stable unsigned 64-bit seed under a versioned domain contract."""
    if not domain or domain.strip() != domain:
        raise ValueError("seed domain must be a non-empty canonical string")
    if not version or version.strip() != version:
        raise ValueError("seed-plan version must be a non-empty canonical string")
    values = (str(master_seed), version, domain, *(str(part) for part in parts))
    payload = _SEED_SEPARATOR.join(values).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


@dataclass(frozen=True)
class SeedPlan:
    """Versioned domain-seed plan recorded with generated artifacts."""

    master_seed: int
    version: str = SEED_PLAN_VERSION

    def for_domain(self, domain: str, *parts: object) -> int:
        if self.version != SEED_PLAN_VERSION:
            raise ValueError(f"unsupported seed-plan version: {self.version}")
        return derive_seed(self.master_seed, domain, *parts, version=self.version)

    def for_decision(
        self, domain: str, stable_entity_id: object, decision_label: object
    ) -> int:
        """Derive a seed using the frozen entity-and-decision tuple shape."""
        return self.for_domain(domain, stable_entity_id, decision_label)


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
        for name, rule in WORLD_SPEC_FIELD_RULES.items():
            value = getattr(self, name)
            if "const" in rule and value != rule["const"]:
                raise ValueError(f"worldgen-1 requires {name}={rule['const']}")
            if "minimum" in rule and value < rule["minimum"]:
                raise ValueError(f"{name} must be at least {rule['minimum']}")
            if "maximum" in rule and value > rule["maximum"]:
                raise ValueError(f"{name} must be at most {rule['maximum']}")
        if self.plate_count < self.continent_count:
            raise ValueError("plate_count must be at least continent_count")

    def budget_estimate(self) -> WorldBudgetEstimate:
        """Return the frozen world/site RAM, disk, and deterministic time estimate."""
        world_cells = self.width * self.height
        local_cells_per_site = (
            self.local_site_width * self.local_site_height * self.local_z_levels
        )
        site_count = self.civilization_count
        total_local_cells = local_cells_per_site * site_count
        # Physical layers coexist; local maps are generated one at a time.
        peak_ram_bytes = world_cells * 8 * 24 + local_cells_per_site * 8 + site_count * 4_096
        # Persisted grids compress variably, so budget against uncompressed int32
        # local cells plus twelve int64-equivalent world layers and envelopes.
        disk_bytes = world_cells * 8 * 12 + total_local_cells * 4 + site_count * 65_536
        physical_work = world_cells * (
            12 + self.erosion_passes + self.climate_relaxation_passes
        )
        history_work = self.history_years * self.history_ticks_per_year * site_count * 250
        total_work = physical_work + total_local_cells + history_work
        whole_milliseconds, remaining_work = divmod(total_work, 1_000)
        time_milliseconds = max(1, whole_milliseconds + (1 if remaining_work else 0))
        return WorldBudgetEstimate(
            WORLD_BUDGET_ALGORITHM_VERSION, site_count, world_cells,
            local_cells_per_site, total_local_cells, peak_ram_bytes, disk_bytes,
            time_milliseconds,
        )

    def estimated_working_set_bytes(self) -> int:
        """Backward-compatible accessor for the typed peak-RAM estimate."""
        return self.budget_estimate().peak_ram_bytes

    def preflight(self, *, max_ram_bytes: int, max_disk_bytes: int | None = None,
                  max_time_milliseconds: int | None = None) -> WorldBudgetEstimate:
        budgets = (("ram", max_ram_bytes, "WG-BUDGET-RAM"),
                   ("disk", max_disk_bytes, "WG-BUDGET-DISK"),
                   ("time", max_time_milliseconds, "WG-BUDGET-TIME"))
        estimate = self.budget_estimate()
        required = {"ram": estimate.peak_ram_bytes, "disk": estimate.disk_bytes,
                    "time": estimate.time_milliseconds}
        for resource, budget, code in budgets:
            if budget is None:
                continue
            if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
                raise ValueError(f"{resource} budget must be a positive integer")
            if required[resource] > budget:
                raise WorldBudgetError(WorldBudgetDiagnostic(
                    code, resource, required[resource], budget, estimate.site_count,
                ))
        return estimate

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
