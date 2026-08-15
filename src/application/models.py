"""Request and result models for the application layer.

Phase 5.5 Section A: Shared data contracts between CLI, overnight mode,
and any future entry points (desktop UI, API server, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..domain.run_spec import RunSpec


@dataclass(frozen=True)
class GenerationRequest:
    """Immutable specification for a single generation run.

    All fields are frozen — two requests with identical values should
    produce identical canonical content (given same models/config).
    """

    seed: int
    title: str = "Untitled World"
    tone: str = "mature_dark_fantasy"
    temperature: float = 0.7
    config_path: str = "config/models.yaml"
    output_dir: str = "tmp/output"
    resume: bool = True  # Resume from checkpoint if available
    # Authoritative procedural world settings. Procedural generation is always
    # the first content stage; narrative/procedural mode switches are obsolete.
    width: int = 1024
    height: int = 1024
    metres_per_world_cell: int = 8_000
    continent_count: int = 1
    history_years: int = 500
    civilization_count: int = 8
    plate_count: int = 24
    minimum_continent_cells: int = 4_096
    history_ticks_per_year: int = 12
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
        from ..domain.run_spec import WorldSpec
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.tone.strip():
            raise ValueError("tone must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be within 0.0..2.0")
        self.to_run_spec()

    def to_run_spec(self) -> "RunSpec":
        """Return the one canonical typed specification used by production."""
        from ..domain.run_spec import RunSpec, WorldSpec
        return RunSpec(
            seed=self.seed, title=self.title, tone=self.tone,
            temperature=self.temperature,
            world=WorldSpec(
            width=self.width, height=self.height,
            metres_per_world_cell=self.metres_per_world_cell,
            continent_count=self.continent_count,
            history_years=self.history_years,
            civilization_count=self.civilization_count,
            plate_count=self.plate_count,
            minimum_continent_cells=self.minimum_continent_cells,
            history_ticks_per_year=self.history_ticks_per_year,
            sea_level_ppm=self.sea_level_ppm,
            axial_tilt_millidegrees=self.axial_tilt_millidegrees,
            erosion_passes=self.erosion_passes,
            climate_relaxation_passes=self.climate_relaxation_passes,
            snapshot_interval_years=self.snapshot_interval_years,
            local_site_width=self.local_site_width,
            local_site_height=self.local_site_height,
            local_z_levels=self.local_z_levels,
            local_cell_millimetres=self.local_cell_millimetres,
        ))

    @classmethod
    def from_run_spec(cls, spec: "RunSpec", *, config_path: str = "config/models.yaml",
                      output_dir: str = "tmp/output", resume: bool = True) -> "GenerationRequest":
        """Rebuild an application request without losing locked world controls."""
        return cls(seed=spec.seed, title=spec.title, tone=spec.tone,
                   temperature=spec.temperature, config_path=config_path,
                   output_dir=output_dir, resume=resume, **spec.world.to_dict())


@dataclass
class GenerationResult:
    """Result of a single generation run.

    Includes the final output, phase timings, RAM profile, and optional package info.
    """

    artifact_id: str
    package_path: str = ""
    package_size: int = 0
    content_hash: str = ""
    phases: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)  # key → hash
    total_duration_seconds: float = 0.0
    peak_ram_mb: int = 0
    ram_budget_mb: int = 0
    errors: list[str] = field(default_factory=list)
    # Phase 5.6 Q5: media completeness (1.0 = all expected assets present).
    # Frozen v2 publication requires both coverage values to be complete.
    image_coverage: float = 1.0
    midi_coverage: float = 1.0
    media_complete: bool = True
