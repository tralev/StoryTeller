"""ImageGenerator interface — generates images from text prompts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ImageGenerator(Protocol):
    """Generates images from text prompts via Stable Diffusion.

    Prompts include the Style Bible suffix appended by the pipeline.
    """

    provider: str
    model_name: str
    quantization: str

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
        steps: int = 20,
    ) -> bytes:
        """Generate an image from a text prompt.

        Args:
            prompt: The image generation prompt.
            negative_prompt: What to avoid in the image.
            size: Output dimensions (width, height).
            seed: RNG seed for reproducibility.
            steps: Diffusion steps (more = higher quality, slower).

        Returns:
            Raw PNG image bytes.
        """
        ...

    async def generate_thumbnail(
        self,
        image_bytes: bytes,
        size: tuple[int, int] = (128, 128),
    ) -> bytes:
        """Generate a thumbnail from a full-size image.

        Args:
            image_bytes: Raw PNG bytes of the full-size image.
            size: Target thumbnail dimensions.

        Returns:
            Raw PNG thumbnail bytes.
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
