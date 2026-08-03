"""Test that all concrete backends satisfy their Protocol interfaces at runtime."""

from __future__ import annotations

import pytest

from src.interfaces import (
    GameMaster,
    ImageGenerator,
    MusicGenerator,
    TextGenerator,
    Validator,
)
from src.backends import (
    AbcMusicGenerator,
    LlamaCppGameMaster,
    LlamaCppTextGenerator,
    LlamaCppValidator,
    SDCppImageGenerator,
)
from src.config import ModelConfig


def _make_config(**overrides: str) -> ModelConfig:
    """Create a minimal ModelConfig for testing."""
    return ModelConfig.from_dict({
        "provider": "test",
        "model": "test-model",
        "quantization": "Q4_K_M",
        **overrides,
    })


class TestBackendProtocols:
    """Verify each backend satisfies its Protocol at runtime."""

    def test_llm_text_generator_satisfies_text_generator(self) -> None:
        backend = LlamaCppTextGenerator(_make_config())
        assert isinstance(backend, TextGenerator), (
            "LlamaCppTextGenerator must satisfy TextGenerator Protocol"
        )

    def test_llm_validator_satisfies_validator(self) -> None:
        backend = LlamaCppValidator(_make_config())
        assert isinstance(backend, Validator), (
            "LlamaCppValidator must satisfy Validator Protocol"
        )

    def test_sd_image_generator_satisfies_image_generator(self) -> None:
        backend = SDCppImageGenerator(_make_config())
        assert isinstance(backend, ImageGenerator), (
            "SDCppImageGenerator must satisfy ImageGenerator Protocol"
        )

    def test_abc_music_generator_satisfies_music_generator(self) -> None:
        backend = AbcMusicGenerator()
        assert isinstance(backend, MusicGenerator), (
            "AbcMusicGenerator must satisfy MusicGenerator Protocol"
        )

    def test_llama_game_master_satisfies_game_master(self) -> None:
        backend = LlamaCppGameMaster(_make_config())
        assert isinstance(backend, GameMaster), (
            "LlamaCppGameMaster must satisfy GameMaster Protocol"
        )


class TestBackendAttributes:
    """Verify backends have required provider/model/quantization attributes."""

    def test_llm_text_generator_attrs(self) -> None:
        backend = LlamaCppTextGenerator(_make_config(
            provider="llama_cpp", model="qwen", quantization="Q4_K_M"
        ))
        assert backend.provider == "llama_cpp"
        assert backend.model_name == "qwen"
        assert backend.quantization == "Q4_K_M"
        assert backend.ram_usage_mb == 4700

    def test_llm_validator_attrs(self) -> None:
        backend = LlamaCppValidator(_make_config(
            provider="llama_cpp", model="phi", quantization="Q4_K_M"
        ))
        assert backend.provider == "llama_cpp"
        assert backend.model_name == "phi"
        assert backend.quantization == "Q4_K_M"
        assert backend.ram_usage_mb == 2200

    def test_sd_image_generator_attrs(self) -> None:
        backend = SDCppImageGenerator(_make_config(
            provider="stable_diffusion_cpp", model="sdxl", quantization="Q8_0"
        ))
        assert backend.provider == "stable_diffusion_cpp"
        assert backend.model_name == "sdxl"
        assert backend.quantization == "Q8_0"
        assert backend.ram_usage_mb == 3500

    def test_abc_music_generator_attrs(self) -> None:
        backend = AbcMusicGenerator()
        assert backend.provider == "abc_notation"

    def test_llama_game_master_attrs(self) -> None:
        backend = LlamaCppGameMaster(_make_config(
            provider="llama_cpp", model="llama-3.2-3b", quantization="Q4_K_M"
        ))
        assert backend.provider == "llama_cpp"
        assert backend.model_name == "llama-3.2-3b"
        assert backend.ram_usage_mb == 2020


class TestAssertImplements:
    """Verify assert_implements() exists on all backends and is callable."""

    def test_llm_text_generator_assert(self) -> None:
        backend = LlamaCppTextGenerator(_make_config())
        backend.assert_implements(TextGenerator)  # Should not raise

    def test_llm_validator_assert(self) -> None:
        backend = LlamaCppValidator(_make_config())
        backend.assert_implements(Validator)  # Should not raise

    def test_sd_image_generator_assert(self) -> None:
        backend = SDCppImageGenerator(_make_config())
        backend.assert_implements(ImageGenerator)  # Should not raise

    def test_abc_music_generator_assert(self) -> None:
        backend = AbcMusicGenerator()
        backend.assert_implements(MusicGenerator)  # Should not raise

    def test_llama_game_master_assert(self) -> None:
        backend = LlamaCppGameMaster(_make_config())
        backend.assert_implements(GameMaster)  # Should not raise


class TestStubErrors:
    """Verify stubs raise NotImplementedError with informative messages."""

    @pytest.mark.asyncio
    async def test_llm_text_generator_requires_load(self) -> None:
        """generate() without load() raises RuntimeError."""
        backend = LlamaCppTextGenerator(_make_config())
        with pytest.raises(RuntimeError, match="Model not loaded"):
            await backend.generate("test prompt")

    @pytest.mark.asyncio
    async def test_llm_validator_validate_raises(self) -> None:
        backend = LlamaCppValidator(_make_config())
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await backend.validate({}, {})

    @pytest.mark.asyncio
    async def test_sd_image_generator_generate_returns_bytes(self) -> None:
        """SDCppImageGenerator.generate() returns valid PNG bytes (placeholder mode)."""
        backend = SDCppImageGenerator(_make_config())
        result = await backend.generate("test prompt", seed=42)
        # Placeholder PNG — should start with PNG header
        assert result[:4] == b"\x89PNG"
        assert len(result) > 100

    async def test_sd_image_generator_thumbnail_works(self) -> None:
        """SDCppImageGenerator.generate_thumbnail() returns smaller PNG."""
        backend = SDCppImageGenerator(_make_config())
        full = await backend.generate("test", seed=42)
        thumb = await backend.generate_thumbnail(full)
        assert len(thumb) < len(full)
        assert thumb[:4] == b"\x89PNG"

    def test_abc_music_generator_init_defaults(self) -> None:
        """AbcMusicGenerator initializes with None seed and empty strings."""
        backend = AbcMusicGenerator()
        assert backend._last_seed is None
        assert backend._last_mood == ""
        assert backend._last_scene_text == ""
