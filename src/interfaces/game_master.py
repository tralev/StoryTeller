"""GameMaster interface — answers reader questions with context-aware responses."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class GameMasterContext:
    """Context assembled for a Game Master query.

    Built by the mobile app at runtime from gm_index.json lookups.
    """

    current_scene: str  # Text of the current CYOA node
    world_rules: str  # Key rules from the World Bible
    relevant_lore: list[dict[str, str]] = field(default_factory=list)
    # Each lore entry: {"name": str, "summary": str}
    # Filtered by reveal_after_node — only entities the reader has unlocked

    visited_nodes: list[str] = field(default_factory=list)
    active_flags: dict[str, bool] = field(default_factory=dict)


@runtime_checkable
class GameMaster(Protocol):
    """Answers reader questions about the story world.

    Runs on mobile via llama.cpp. Context is assembled dynamically
    from gm_index.json lookups before each query.
    """

    provider: str
    model_name: str
    quantization: str

    async def answer(
        self,
        question: str,
        context: GameMasterContext,
    ) -> AsyncIterator[str]:
        """Answer a reader's question, streaming the response.

        Args:
            question: The reader's question.
            context: Assembled context including current scene,
                     relevant lore, and world rules.

        Yields:
            Response tokens as they are generated.
        """
        ...

    async def load(self) -> None:
        """Load the model into memory."""
        ...

    async def unload(self) -> None:
        """Unload the model to free RAM."""
        ...

    @property
    def ram_usage_mb(self) -> int:
        """Estimated RAM usage in MB."""
        ...
