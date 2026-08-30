"""TextGenerator interface — generates structured text from prompt templates."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TextGenerator(Protocol):
    """Generates structured text output from prompts.

    Used for: World Bible, Style Bible, Story, Decision Points,
    Graph Skeleton, Node Text, Image Prompts, ABC Notation.
    """

    provider: str
    model_name: str
    quantization: str

    async def generate(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate structured output from a prompt.

        Args:
            prompt: The formatted prompt string (from Jinja2 template).
            schema: Optional JSON Schema the output must conform to.
            temperature: Sampling temperature (0.0 = deterministic).
            seed: RNG seed for reproducibility.
            max_tokens: Maximum tokens to generate.

        Returns:
            Parsed JSON dict matching the schema.

        Raises:
            GenerationError: If generation fails or output doesn't match schema.
        """
        ...

    def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """Generate text with token-by-token streaming.

        Used for Game Master responses on mobile.

        Returns:
            Async iterator yielding tokens as they are generated.
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
