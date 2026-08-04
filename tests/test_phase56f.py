"""Phase 5.6F: Provider factories — registry-based adapter selection, strict parsing.

Verifies:
  1. Built-in providers (llama_cpp, stable_diffusion_cpp, abc-notation) registered
  2. create_text() with known provider returns backend
  3. create_text() with unknown provider raises ConfigurationError (strict=True)
  4. create_text() with unknown provider returns stub (strict=False)
  5. create_image() with known/unknown providers
  6. create_music() returns AbcMusicGenerator
  7. create_validator() returns deterministic when model unavailable
  8. Custom provider registration works
  9. list_text_providers / list_all_providers introspection
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.config import ModelConfig
from src.pipeline.errors import ConfigurationError


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_config(provider: str) -> ModelConfig:
    return ModelConfig(
        provider=provider, model="test", quantization="Q4_K_M",
        repo="test/test", file="test.gguf",
    )


# ── Unit: Built-in providers ────────────────────────────────────────────────


class TestBuiltInProviders:
    """Default providers are registered at module load."""

    def test_known_text_providers(self) -> None:
        from src.backends.registry import ProviderRegistry
        providers = ProviderRegistry.list_text_providers()
        assert "llama_cpp" in providers

    def test_known_image_providers(self) -> None:
        from src.backends.registry import ProviderRegistry
        providers = ProviderRegistry.list_image_providers()
        assert "stable_diffusion_cpp" in providers

    def test_known_music_providers(self) -> None:
        from src.backends.registry import ProviderRegistry
        all_providers = ProviderRegistry.list_all_providers()
        assert "abc-notation" in all_providers["music"]

    def test_list_all_returns_categories(self) -> None:
        from src.backends.registry import ProviderRegistry
        all_p = ProviderRegistry.list_all_providers()
        for cat in ["text", "image", "music", "validator"]:
            assert cat in all_p, f"Missing category: {cat}"
            assert isinstance(all_p[cat], list)


# ── Unit: Strict mode — unknown providers ────────────────────────────────────


class TestStrictMode:
    """Strict=True raises ConfigurationError for unknown providers."""

    def test_unknown_text_provider_strict_raises(self) -> None:
        from src.backends.registry import ProviderRegistry
        config = _make_config("ollama")  # Not registered
        with pytest.raises(ConfigurationError) as exc_info:
            ProviderRegistry.create_text(config, strict=True)
        error = exc_info.value
        assert "ollama" in str(error)
        assert error.code == "CFG_001"

    def test_unknown_image_provider_strict_raises(self) -> None:
        from src.backends.registry import ProviderRegistry
        config = _make_config("comfy_ui")
        with pytest.raises(ConfigurationError) as exc_info:
            ProviderRegistry.create_image(config, strict=True)
        assert "comfy_ui" in str(exc_info.value)

    def test_unknown_text_provider_non_strict_returns_stub(self) -> None:
        from src.backends.registry import ProviderRegistry
        config = _make_config("unknown_provider")
        gen = ProviderRegistry.create_text(config, strict=False)
        assert gen is not None
        assert gen.provider == "stub"
        with pytest.raises(RuntimeError, match="No text backend"):
            import asyncio
            asyncio.run(gen.generate(prompt="test"))

    def test_unknown_image_provider_non_strict_returns_stub(self) -> None:
        from src.backends.registry import ProviderRegistry
        config = _make_config("unknown_img")
        gen = ProviderRegistry.create_image(config, strict=False)
        assert gen.provider == "stub"


# ── Unit: Known provider creation ────────────────────────────────────────────


class TestKnownProviderCreation:
    """create_*() with known providers returns correct backends."""

    def test_create_music_returns_abc_music_generator(self) -> None:
        from src.backends.registry import ProviderRegistry
        config = ModelConfig(provider="abc-notation", model="via-text",
                             quantization="")
        gen = ProviderRegistry.create_music(config)
        assert gen is not None
        assert hasattr(gen, "validate_abc")
        assert hasattr(gen, "abc_to_midi")

    def test_create_validator_returns_llama_cpp_object(self) -> None:
        """create_validator returns a LlamaCppTextGenerator. Model load
        failure happens at load() time, not factory time."""
        from src.backends.registry import ProviderRegistry
        config = _make_config("llama_cpp")
        gen = ProviderRegistry.create_validator(config, strict=True)
        # Factory creates the object — model not loaded yet
        assert gen is not None
        assert gen.provider == "llama_cpp"

    def test_create_validator_unknown_provider_returns_deterministic(self) -> None:
        """Unknown validator provider (with empty provider string) returns deterministic."""
        from src.backends.registry import ProviderRegistry
        config = ModelConfig(provider="", model="none", quantization="")
        gen = ProviderRegistry.create_validator(config, strict=True)
        assert gen.provider == "deterministic"
        assert gen.ram_usage_mb == 0

    def test_create_text_strict_known_returns_backend(self) -> None:
        from src.backends.registry import ProviderRegistry
        config = _make_config("llama_cpp")
        gen = ProviderRegistry.create_text(config, strict=True)
        assert gen.provider == "llama_cpp"
        assert gen.model_name == "test"


# ── Unit: Custom provider registration ───────────────────────────────────────


class TestCustomProviderRegistration:
    """Custom providers can be registered at runtime."""

    def test_register_and_create_custom_text_provider(self) -> None:
        from src.backends.registry import ProviderRegistry

        class CustomTextGen:
            provider = "custom_vllm"
            model_name = "custom"
            quantization = "Q4"
            ram_usage_mb = 1000
            async def load(self) -> None: pass
            async def unload(self) -> None: pass
            async def generate(self, **kw: Any) -> dict[str, Any]:
                return {"text": "custom output"}

        ProviderRegistry.register_text("custom_vllm", lambda c: CustomTextGen())

        config = _make_config("custom_vllm")
        gen = ProviderRegistry.create_text(config, strict=True)
        assert gen.provider == "custom_vllm"

        # Clean up
        ProviderRegistry._text_factories.pop("custom_vllm", None)

    def test_registered_provider_appears_in_list(self) -> None:
        from src.backends.registry import ProviderRegistry

        ProviderRegistry.register_text("temp_test_provider", lambda c: None)
        providers = ProviderRegistry.list_text_providers()
        assert "temp_test_provider" in providers

        # Clean up
        ProviderRegistry._text_factories.pop("temp_test_provider", None)


# ── Integration: ProviderRegistry used in full pipeline ──────────────────────


class TestProviderRegistryIntegration:
    """Full pipeline uses ProviderRegistry under the hood."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "docs" / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas directory not found")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_pipeline_uses_registry(self, tmp_path: Path) -> None:
        """GenerateStory creates all backends via ProviderRegistry."""
        from src.application.generate_story import GenerateStory
        from .test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedTextGenerator,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            _clear_fakes,
            _inject_fakes,
        )

        _clear_fakes()
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        from src.application.models import GenerationRequest

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42, title="Registry Test", tone="dark_fantasy",
            output_dir=str(tmp_path / "output"), config_path="/nonexistent",
            resume=False,
        )

        result = await service.execute(request)
        assert not result.errors, f"Errors: {result.errors}"
        assert result.package_path
