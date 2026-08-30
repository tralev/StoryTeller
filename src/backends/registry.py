"""Provider Registry — registry-based backend selection with strict config parsing.

Phase 5.6F: Replaces ad-hoc try/except chains in GenerateStory._create_*()
with a centralized registry that maps provider names to factory functions.

Supports:
  - Known providers registered at module load time
  - Custom provider registration at runtime
  - Strict mode: rejects unknown providers with ConfigurationError
  - Lazy import: factories only import backends when called

Usage:
    from src.backends.registry import ProviderRegistry

    text_gen = ProviderRegistry.create_text(config.text_generator, strict=True)
    image_gen = ProviderRegistry.create_image(config.image_generator, strict=True)
    music_gen = ProviderRegistry.create_music(config.music_generator)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..config import ModelConfig
from ..pipeline.errors import ConfigurationError

# ── factory function signatures ──────────────────────────────────────────

TextFactory = Callable[[ModelConfig], Any]
ImageFactory = Callable[[ModelConfig], Any]
MusicFactory = Callable[[], Any]
ValidatorFactory = Callable[[ModelConfig], Any]


class ProviderRegistry:
    """Centralized registry for backend provider factories.

    Usage:
        # Default registration (happens at module load)
        ProviderRegistry.register_text("llama_cpp", _build_llama_text)

        # Create a backend
        gen = ProviderRegistry.create_text(config, strict=True)

        # List known providers
        names = ProviderRegistry.list_text_providers()
    """

    _text_factories: dict[str, TextFactory] = {}
    _image_factories: dict[str, ImageFactory] = {}
    _music_factories: dict[str, MusicFactory] = {}
    _validator_factories: dict[str, ValidatorFactory] = {}

    # ── registration ──────────────────────────────────────────────────

    @classmethod
    def register_text(cls, provider: str, factory: TextFactory) -> None:
        """Register a text generator factory."""
        cls._text_factories[provider] = factory

    @classmethod
    def register_image(cls, provider: str, factory: ImageFactory) -> None:
        """Register an image generator factory."""
        cls._image_factories[provider] = factory

    @classmethod
    def register_music(cls, provider: str, factory: MusicFactory) -> None:
        """Register a music generator factory."""
        cls._music_factories[provider] = factory

    @classmethod
    def register_validator(cls, provider: str, factory: ValidatorFactory) -> None:
        """Register a validator factory."""
        cls._validator_factories[provider] = factory

    # ── creation (strict mode) ────────────────────────────────────────

    @classmethod
    def create_text(
        cls,
        config: ModelConfig,
        *,
        strict: bool = True,
    ) -> Any:
        """Create a text generator from config.

        Args:
            config: ModelConfig with provider field.
            strict: If True, raises ConfigurationError for unknown providers.
                    If False, returns a stub.

        Returns:
            A TextGenerator-compatible instance.

        Raises:
            ConfigurationError: If strict=True and provider is unknown.
        """
        factory = cls._text_factories.get(config.provider)
        if factory is not None:
            return factory(config)

        if strict:
            raise ConfigurationError(
                "models.yaml#text",
                f"Unknown provider: '{config.provider}'. Known: {sorted(cls._text_factories)}",
            )
        return _stub_text_gen()

    @classmethod
    def create_image(
        cls,
        config: ModelConfig,
        *,
        strict: bool = True,
    ) -> Any:
        """Create an image generator from config.

        Args:
            config: ModelConfig with provider field.
            strict: If True, raises ConfigurationError for unknown providers.

        Returns:
            An ImageGenerator-compatible instance.

        Raises:
            ConfigurationError: If strict=True and provider is unknown.
        """
        factory = cls._image_factories.get(config.provider)
        if factory is not None:
            return factory(config)

        if strict:
            raise ConfigurationError(
                "models.yaml#image",
                f"Unknown provider: '{config.provider}'. Known: {sorted(cls._image_factories)}",
            )
        return _stub_image_gen()

    @classmethod
    def create_music(cls, config: ModelConfig) -> Any:
        """Create a music generator from config.

        Music generation uses either abc-notation (built-in) or
        a registered provider.

        Returns:
            A MusicGenerator-compatible instance.
        """
        factory = cls._music_factories.get(config.provider)
        if factory is not None:
            return factory()
        # Fallback: built-in ABC music generator
        return _default_music_gen()

    @classmethod
    def create_validator(
        cls,
        config: ModelConfig,
        *,
        strict: bool = True,
    ) -> Any:
        """Create a validator backend from config.

        Returns a deterministic-only validator if no LLM is available.

        Args:
            config: ModelConfig with provider field.
            strict: If True, raises for unknown providers.

        Returns:
            A Validator-compatible instance.

        Raises:
            ConfigurationError: If strict=True and provider is unknown.
        """
        factory = cls._validator_factories.get(config.provider)
        if factory is not None:
            try:
                return factory(config)
            except Exception:
                pass

        if strict and config.provider not in cls._validator_factories:
            if config.provider:
                raise ConfigurationError(
                    "models.yaml#validator",
                    f"Unknown provider: '{config.provider}'. "
                    f"Known: {sorted(cls._validator_factories)}",
                )
        return _deterministic_validator()

    # ── introspection ──────────────────────────────────────────────────

    @classmethod
    def list_text_providers(cls) -> list[str]:
        """List registered text generator providers."""
        return sorted(cls._text_factories)

    @classmethod
    def list_image_providers(cls) -> list[str]:
        """List registered image generator providers."""
        return sorted(cls._image_factories)

    @classmethod
    def list_all_providers(cls) -> dict[str, list[str]]:
        """Return all registered providers by category."""
        return {
            "text": cls.list_text_providers(),
            "image": cls.list_image_providers(),
            "music": sorted(cls._music_factories),
            "validator": sorted(cls._validator_factories),
        }


# ── built-in factory functions (lazy imports) ──────────────────────────────


def _build_llama_text(config: ModelConfig) -> Any:
    """Build a LlamaCppTextGenerator."""
    from .llm_backend import LlamaCppTextGenerator

    return LlamaCppTextGenerator(config)


def _build_sd_image(config: ModelConfig) -> Any:
    """Build an SDCppImageGenerator."""
    from .image_backend import SDCppImageGenerator

    return SDCppImageGenerator(config)


def _build_abc_music() -> Any:
    """Build an AbcMusicGenerator."""
    from .midi_backend import AbcMusicGenerator

    return AbcMusicGenerator()


def _build_llama_validator(config: ModelConfig) -> Any:
    """Build an LLM-based validator (uses same backend as text)."""
    from .llm_backend import LlamaCppTextGenerator

    return LlamaCppTextGenerator(config)


# ── stubs ──────────────────────────────────────────────────────────────────


def _stub_text_gen() -> Any:
    class _Stub:
        provider: str = "stub"
        model_name: str = "mock"
        quantization: str = ""
        ram_usage_mb: int = 0

        async def generate(self, prompt: str = "", **kw: Any) -> dict[str, Any]:
            raise RuntimeError("No text backend loaded")

        def generate_stream(self, prompt: str = "", **kw: Any) -> Any:
            raise RuntimeError("No text backend")

        async def load(self) -> None:
            pass

        async def unload(self) -> None:
            pass

    return _Stub()


def _stub_image_gen() -> Any:
    class _Stub:
        provider: str = "stub"
        model_name: str = "mock"
        quantization: str = ""
        ram_usage_mb: int = 0

        async def generate(self, prompt: str = "", **kw: Any) -> bytes:
            raise RuntimeError("No image backend")

        async def generate_thumbnail(self, image_bytes: bytes = b"", **kw: Any) -> bytes:
            return b""

        async def load(self) -> None:
            pass

        async def unload(self) -> None:
            pass

    return _Stub()


def _deterministic_validator() -> Any:
    """A validator with no model dependency — 0 RAM."""

    class _Det:
        provider: str = "deterministic"
        model_name: str = "rule-based"
        quantization: str = ""
        ram_usage_mb: int = 0

        async def load(self) -> None:
            pass

        async def unload(self) -> None:
            pass

    return _Det()


def _default_music_gen() -> Any:
    return _build_abc_music()


# ── register built-in providers ────────────────────────────────────────────

ProviderRegistry.register_text("llama_cpp", _build_llama_text)
ProviderRegistry.register_image("stable_diffusion_cpp", _build_sd_image)
ProviderRegistry.register_music("abc-notation", _build_abc_music)
ProviderRegistry.register_validator("llama_cpp", _build_llama_validator)
