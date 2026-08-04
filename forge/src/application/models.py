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
    output_dir: str = "output"
    resume: bool = True  # Resume from checkpoint if available
    # Phase 7.5: Procedural world generation
    world_mode: str = "narrative"  # "narrative" | "procedural" | "hybrid"
    world_size: int = 64
    history_years: int = 200
    max_civs: int = 4


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
