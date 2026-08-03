from __future__ import annotations

"""Concrete LLM backend using llama-cpp-python.

Implements both TextGenerator and Validator interfaces.
In Phase 1, these are stubs that raise NotImplementedError.
Real implementation will load GGUF models via llama-cpp-python.
"""

from typing import Any, AsyncIterator

from ..config import ModelConfig
from ..interfaces import (
    ConsistencyReport,
    TextGenerator,
    ValidationResult,
    Validator,
)


class LlamaCppTextGenerator:
    """Text generation via llama-cpp-python.

    Stub implementation — raises NotImplementedError until Phase 4
    when real model inference is needed.
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

    async def generate(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate structured output from a prompt.

        Currently a stub. In Phase 4, this will:
        1. Load the GGUF model via llama-cpp-python
        2. Call create_completion with JSON mode
        3. Parse and validate the JSON response
        """
        raise NotImplementedError(
            "LlamaCppTextGenerator.generate() is a stub. "
            "Real LLM inference will be implemented in Phase 4."
        )

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        """Generate text with token-by-token streaming."""
        raise NotImplementedError(
            "LlamaCppTextGenerator.generate_stream() is a stub. "
            "Real streaming will be implemented in Phase 4."
        )

    async def load(self) -> None:
        """Load the model into memory."""
        self._loaded = True

    async def unload(self) -> None:
        """Unload the model to free RAM."""
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 4700  # Approximate for Qwen 7B Q4_K_M

    def assert_implements(self, interface: type) -> None:
        """Verify this class satisfies the given Protocol at runtime."""
        pass  # Protocols are structural — checked by static type checker


class LlamaCppValidator:
    """Validation via a separate llama-cpp-python model.

    Uses a different model (Phi-3.5-mini) than the generator
    for independent critique.
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

    async def validate(
        self,
        content: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """Validate content against schema and business rules."""
        raise NotImplementedError(
            "LlamaCppValidator.validate() is a stub. "
            "Real validation will be implemented in Phase 4."
        )

    async def consistency_check(
        self,
        text: str,
        bible: dict[str, Any],
    ) -> ConsistencyReport:
        """Check if text contradicts the World Bible."""
        raise NotImplementedError(
            "LlamaCppValidator.consistency_check() is a stub."
        )

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 2200  # Approximate for Phi-3.5-mini Q4_K_M

    def assert_implements(self, interface: type) -> None:
        """Verify this class satisfies the given Protocol at runtime."""
        pass  # Protocols are structural — checked by static type checker
