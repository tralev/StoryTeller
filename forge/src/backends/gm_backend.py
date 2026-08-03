"""Concrete Game Master backend using llama-cpp-python.

Implements the GameMaster Protocol for on-device (mobile) question answering.
Stub implementation until Phase 6 when mobile integration is needed.
"""

from __future__ import annotations

from typing import AsyncIterator

from ..config import ModelConfig
from ..interfaces import GameMasterContext


class LlamaCppGameMaster:
    """Game Master for mobile via llama.cpp.

    Runs on-device with ~2 GB RAM (Llama 3.2 3B Q4_K_M).
    Context is assembled dynamically from gm_index.json lookups.

    Stub implementation — raises NotImplementedError until Phase 6
    when llama.cpp mobile bindings are integrated.
    """

    provider: str
    model_name: str
    quantization: str

    def __init__(self, config: ModelConfig) -> None:
        self.provider = config.provider
        self.model_name = config.model
        self.quantization = config.quantization
        self._config = config
        self._loaded = False

    async def answer(
        self,
        question: str,
        context: GameMasterContext,
    ) -> AsyncIterator[str]:
        """Answer a reader's question, streaming the response.

        Stub — in Phase 6, this will:
        1. Assemble the GM prompt from context (current_scene, world_rules,
           relevant_lore filtered by reveal_after_node)
        2. Call llama.cpp with streaming mode
        3. Yield tokens as they arrive

        Raises:
            NotImplementedError: Always in Phase 1-5.
        """
        # Use question and context to avoid unused-argument warnings
        _ = question
        _ = context
        raise NotImplementedError(
            "LlamaCppGameMaster.answer() is a stub. "
            "Real Game Master integration will be implemented in Phase 6."
        )
        yield  # pragma: no cover (unreachable, satisfies AsyncIterator return)

    async def load(self) -> None:
        """Load the model into memory."""
        self._loaded = True

    async def unload(self) -> None:
        """Unload the model to free RAM."""
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 2020  # Approximate for Llama 3.2 3B Q4_K_M
