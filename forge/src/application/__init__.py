"""StoryTeller Forge — Application Services.

Phase 5.5 Section A: Shared application layer — both CLI and overnight
mode invoke the same GenerateStory service instead of duplicating
pipeline assembly.

Usage:
    from src.application import GenerateStory, GenerationRequest

    service = GenerateStory()
    request = GenerationRequest(seed=42, title="The Crystal Accord", tone="heroic_fantasy")
    result = await service.execute(request)
"""

from __future__ import annotations

from .models import GenerationRequest, GenerationResult
from .generate_story import GenerateStory

__all__ = ["GenerateStory", "GenerationRequest", "GenerationResult"]
