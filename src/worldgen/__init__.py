"""Worldgen — procedural world generation for StoryTeller.

Phase 7.5: Generates physically coherent fantasy worlds using
deterministic algorithms (terrain, climate, biomes, civilization
simulation). The output feeds into WorldBuilder as structured
constraints for LLM enrichment.

The legacy snapshot API remains a compatibility island for Phase 2. New code
uses the deterministic numeric, artifact and stage contracts exported here.
"""

from __future__ import annotations

from .generator import generate_world
from .models import WorldSnapshot
from .step import ProceduralWorldStep
from .numeric import SplitMix64, checked_i64, div_round_half_up, mul_ppm, rng_for, stable_id
from .artifacts import (
    DependencyGraph, GridChunk, WorldArtifact, WorldArtifactRepository, canonical_json,
)
from .stages import WorldStage, WorldStageRunner
from .grid import Coordinate, GridSpec, IntGrid
from .physical_pipeline import generate_physical_world

__all__ = [
    "generate_world",
    "ProceduralWorldStep",
    "WorldSnapshot",
    "SplitMix64", "checked_i64", "div_round_half_up", "mul_ppm", "rng_for",
    "stable_id", "DependencyGraph", "GridChunk", "WorldArtifact", "WorldArtifactRepository",
    "canonical_json",
    "WorldStage", "WorldStageRunner", "Coordinate", "GridSpec", "IntGrid",
    "generate_physical_world",
]
