"""Request and result models for the application layer.

Phase 5.5 Section A: Shared data contracts between CLI, overnight mode,
and any future entry points (desktop UI, API server, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GenerationRequest:
    """Immutable specification for a single generation run.

    All fields are frozen — two requests with identical values should
    produce identical canonical content (given same models/config).
    """

    seed: int
    title: str = "Untitled World"
    tone: str = "dark_fantasy"
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

    def __post_init__(self) -> None:
        from ..domain.run_spec import WorldSpec
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.tone.strip():
            raise ValueError("tone must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be within 0.0..2.0")
        WorldSpec(
            width=self.width, height=self.height,
            metres_per_world_cell=self.metres_per_world_cell,
            continent_count=self.continent_count,
            history_years=self.history_years,
            civilization_count=self.civilization_count,
        )


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
    # A package can be accepted yet incomplete (e.g. MIDI at 90% vs 80% min).
    image_coverage: float = 1.0
    midi_coverage: float = 1.0
    media_complete: bool = True
