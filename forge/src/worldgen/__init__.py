"""Worldgen — procedural world generation for StoryTeller.

Phase 7.5: Generates physically coherent fantasy worlds using
deterministic algorithms (terrain, climate, biomes, civilization
simulation). The output feeds into WorldBuilder as structured
constraints for LLM enrichment.

Three generation modes:
  - narrative: LLM-first (current default, no worldgen)
  - procedural: worldgen first, LLM enrichment after
  - hybrid: user constraints + worldgen + LLM narrative
"""

from __future__ import annotations

from .generator import generate_world
from .models import WorldSnapshot
from .step import ProceduralWorldStep

__all__ = [
    "generate_world",
    "ProceduralWorldStep",
    "WorldSnapshot",
]
