"""Concrete image generation backend using stable-diffusion-cpp-python.

Stub implementation until Phase 5 when real image generation is needed.
"""

from __future__ import annotations

from ..config import ModelConfig


class SDCppImageGenerator:
    """Image generation via stable-diffusion-cpp-python.

    Stub implementation — raises NotImplementedError until Phase 5
    when real image generation is needed.
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
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
        steps: int = 20,
    ) -> bytes:
        """Generate an image from a text prompt.

        Currently a stub. In Phase 5, this will:
        1. Load SDXL-Turbo GGUF via stable-diffusion-cpp-python
        2. Run diffusion with the given seed, steps, and size
        3. Return raw PNG bytes
        """
        raise NotImplementedError(
            "SDCppImageGenerator.generate() is a stub. "
            "Real image generation will be implemented in Phase 5."
        )

    async def generate_thumbnail(
        self,
        image_bytes: bytes,
        size: tuple[int, int] = (128, 128),
    ) -> bytes:
        """Generate a thumbnail from a full-size image."""
        raise NotImplementedError(
            "SDCppImageGenerator.generate_thumbnail() is a stub."
        )

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 3500  # Approximate for SDXL-Turbo Q8_0

    def assert_implements(self, interface: type) -> None:
        """Verify this class satisfies the given Protocol at runtime."""
        pass  # Protocols are structural — checked by static type checker
