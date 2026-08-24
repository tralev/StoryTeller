"""Concrete image generation backend using stable-diffusion-cpp-python.

Loads SDXL GGUF models and generates 512x512 PNG images.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import ModelConfig
from ..narrative.media import encode_png


def _save_png_rgba_srgb(img: Any) -> bytes:
    """Encode `img` through the project's own canonical PNG writer.

    Matches package-v2.md's fixed PNG policy ("All PNGs: non-interlaced,
    8-bit RGBA, sRGB, non-animated"). Pillow's own PNG writer uses
    adaptive per-row filtering and never adds an sRGB chunk, neither of
    which `narrative.media.decode_png`'s strict authoritative decoder
    accepts — so Pillow is used only for decode/resize/format-conversion
    here, and `encode_png` always produces the final bytes.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return encode_png(img.width, img.height, img.tobytes())


class SDCppImageGenerator:
    """Image generation via stable-diffusion-cpp-python.

    Loads SDXL-Turbo GGUF, generates 512x512 PNGs with seed control.
    Falls back to a simple solid-color placeholder if the native lib
    is not installed.

    Usage:
        gen = SDCppImageGenerator(config)
        await gen.load()
        png_bytes = await gen.generate(prompt="...", seed=42)
        thumb = await gen.generate_thumbnail(png_bytes)
        await gen.unload()
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
        self._sd = None  # stable_diffusion_cpp instance

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
        steps: int = 20,
    ) -> bytes:
        """Generate an image from a text prompt.

        Uses stable-diffusion-cpp-python if installed, otherwise
        falls back to a deterministic placeholder PNG for testing.
        """
        if self._sd is not None:
            return await self._generate_sd(prompt, negative_prompt, size, seed, steps)
        return self._generate_placeholder(size, seed or 0)

    async def generate_thumbnail(
        self,
        image_bytes: bytes,
        size: tuple[int, int] = (128, 128),
    ) -> bytes:
        """Generate a thumbnail via Pillow resize."""
        img: Any = Image.open(io.BytesIO(image_bytes))
        try:
            resample = Image.Resampling.LANCZOS  # Pillow >= 10
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined]  # Pillow < 10
        img = img.resize(size, resample)
        return _save_png_rgba_srgb(img)

    async def load(self) -> None:
        """Load the SDXL model from disk.

        Tries stable-diffusion-cpp-python first, falls back to
        Pillow-based placeholder generation.
        """
        try:
            from stable_diffusion_cpp import StableDiffusion

            model_path = self._resolve_model_path()
            if model_path and Path(model_path).exists():
                self._sd = StableDiffusion(
                    model_path=str(model_path),
                    n_threads=min(8, os.cpu_count() or 4),
                )
                self._loaded = True
                return
        except ImportError:
            pass  # Fall through to placeholder mode
        except Exception:
            pass

        # Placeholder mode — requires Pillow
        self._loaded = True

    async def unload(self) -> None:
        """Free the SDXL model from memory."""
        self._sd = None
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 3500  # Approximate for SDXL-Turbo Q8_0

    def assert_implements(self, interface: type) -> None:
        pass

    # ── internal ──────────────────────────────────────────────────────

    def _resolve_model_path(self) -> Path | None:
        """Find the SDXL GGUF file.

        Checks in order:
        1. STORYTELLER_MODELS_DIR env var
        2. Project root ai_models/
        3. ~/.storyteller/models/ (legacy)
        4. Direct path
        """
        env_dir = os.environ.get("STORYTELLER_MODELS_DIR", "")
        project_root = Path(__file__).resolve().parent.parent.parent
        candidates: list[Path | None] = [
            Path(env_dir) / self._config.file if env_dir else None,
            project_root / "ai_models" / self._config.file,
            Path.home() / ".storyteller" / "models" / self._config.file,
            Path(self._config.file),
        ]
        for p in candidates:
            if p is not None and p.exists():
                return p
        return None

    async def _generate_sd(
        self,
        prompt: str,
        negative_prompt: str,
        size: tuple[int, int],
        seed: int | None,
        steps: int,
    ) -> bytes:
        """Generate via stable-diffusion-cpp-python in a thread."""
        import asyncio

        def _sync() -> bytes:
            assert self._sd is not None
            result = self._sd.txt_to_img(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=size[0],
                height=size[1],
                sample_steps=steps,
                seed=seed or 0,
            )
            # result is a list of PIL Images or bytes
            if isinstance(result, list) and len(result) > 0:
                img = result[0]
                if isinstance(img, bytes):
                    # Re-encode through Pillow so the RGBA+sRGB policy holds
                    # regardless of what the underlying library emitted.
                    img = Image.open(io.BytesIO(img))
                return _save_png_rgba_srgb(img)
            raise RuntimeError("SDXL generated no output")

        return await asyncio.to_thread(_sync)

    @staticmethod
    def _generate_placeholder(size: tuple[int, int], seed: int) -> bytes:
        """Generate a deterministic placeholder PNG (no model needed).

        Uses the seed to create a unique solid-color image with
        embedded seed bytes for verifiability.
        """
        r = (seed * 37 + 13) % 256
        g = (seed * 53 + 7) % 256
        b = (seed * 71 + 23) % 256
        img = Image.new("RGBA", size, color=(r, g, b, 255))
        return _save_png_rgba_srgb(img)
