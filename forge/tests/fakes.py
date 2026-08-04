"""Shared typed fake generators for tests.

Phase 5.5G: These implement ALL protocol members (provider, model_name,
quantization, generate, generate_stream, load, unload, ram_usage_mb)
so they pass strict mypy type checking when passed where TextGenerator,
ImageGenerator, or Validator is expected. Previously, each test file
created partial mocks that mypy rejected with arg-type errors.

Usage:
    from tests.fakes import FakeTextGenerator, FakeImageGenerator

    gen = FakeTextGenerator()
    step = WorldBuilder(generator=gen, config=config)  # passes mypy ✓
"""

from __future__ import annotations

from typing import Any, AsyncIterator


class FakeTextGenerator:
    """Fully typed fake TextGenerator for testing.

    Implements all TextGenerator protocol members. Accepts fixtures
    or callbacks for custom behavior.
    """

    provider: str = "fake"
    model_name: str = "fake-text"
    quantization: str = "Q4_K_M"

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self._responses = responses or []
        self._idx = 0
        self._loaded = False
        self.call_count = 0

    async def generate(
        self,
        prompt: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        self.call_count += 1
        if self._idx < len(self._responses):
            result = self._responses[self._idx]
            self._idx += 1
            return result
        return {"text": "fake response"}

    def generate_stream(
        self,
        prompt: str = "",
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> AsyncIterator[str]:
        async def _stream() -> AsyncIterator[str]:
            yield "fake"
            yield " stream"
        return _stream()

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 4700


class FakeImageGenerator:
    """Fully typed fake ImageGenerator for testing."""

    provider: str = "fake"
    model_name: str = "fake-image"
    quantization: str = "Q8_0"

    def __init__(self) -> None:
        self._loaded = False
        self.call_count = 0

    async def generate(
        self,
        prompt: str = "",
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
    ) -> bytes:
        self.call_count += 1
        # Minimal valid PNG (1x1 pixel)
        return (
            b"\x89PNG\r\n\x1a\n"  # PNG header
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
            b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    async def generate_thumbnail(
        self,
        image_bytes: bytes = b"",
        size: tuple[int, int] = (128, 128),
    ) -> bytes:
        return image_bytes  # Return same bytes for test

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 5000


class FakeValidator:
    """Fully typed fake Validator for testing."""

    provider: str = "fake"
    model_name: str = "fake-validator"
    quantization: str = "Q4_K_M"

    def __init__(self, should_fail: bool = False) -> None:
        self._loaded = False
        self.should_fail = should_fail
        self.call_count = 0

    async def validate(
        self,
        content: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:  # ValidationResult
        self.call_count += 1
        from src.interfaces import ValidationResult
        if self.should_fail:
            return ValidationResult(is_valid=False, errors=["fake validation error"])
        return ValidationResult(is_valid=True)

    async def consistency_check(
        self,
        text: str,
        bible: dict[str, Any],
    ) -> Any:  # ConsistencyReport
        from src.interfaces import ConsistencyReport
        return ConsistencyReport(is_consistent=True)

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 2200


class FakeMusicGenerator:
    """Fully typed fake MusicGenerator for testing."""

    provider: str = "fake"
    model_name: str = "fake-music"
    quantization: str = ""

    def validate_abc(self, abc_text: str) -> bool:
        return len(abc_text) > 10

    def abc_to_midi(self, abc_text: str) -> bytes:
        # Minimal MIDI file
        return (
            b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x80"
            b"MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
        )
