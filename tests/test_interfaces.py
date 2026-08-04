"""Test that all model interfaces are properly defined and importable."""

import pytest

from src.interfaces import (
    ConsistencyReport,
    GameMaster,
    GameMasterContext,
    ImageGenerator,
    MusicGenerator,
    TextGenerator,
    ValidationResult,
    Validator,
)


class TestInterfacesExist:
    """Verify all interfaces are importable and have expected attributes."""

    def test_text_generator_protocol(self) -> None:
        """TextGenerator Protocol has required methods."""
        assert hasattr(TextGenerator, "generate")
        assert hasattr(TextGenerator, "generate_stream")
        assert hasattr(TextGenerator, "load")
        assert hasattr(TextGenerator, "unload")
        assert hasattr(TextGenerator, "ram_usage_mb")

    def test_validator_protocol(self) -> None:
        """Validator Protocol has required methods."""
        assert hasattr(Validator, "validate")
        assert hasattr(Validator, "consistency_check")
        assert hasattr(Validator, "load")
        assert hasattr(Validator, "unload")
        assert hasattr(Validator, "ram_usage_mb")

    def test_image_generator_protocol(self) -> None:
        """ImageGenerator Protocol has required methods."""
        assert hasattr(ImageGenerator, "generate")
        assert hasattr(ImageGenerator, "generate_thumbnail")
        assert hasattr(ImageGenerator, "load")
        assert hasattr(ImageGenerator, "unload")
        assert hasattr(ImageGenerator, "ram_usage_mb")

    def test_music_generator_protocol(self) -> None:
        """MusicGenerator Protocol has required methods."""
        assert hasattr(MusicGenerator, "generate")
        assert hasattr(MusicGenerator, "abc_to_midi")
        assert hasattr(MusicGenerator, "validate_abc")

    def test_game_master_protocol(self) -> None:
        """GameMaster Protocol has required methods."""
        assert hasattr(GameMaster, "answer")
        assert hasattr(GameMaster, "load")
        assert hasattr(GameMaster, "unload")
        assert hasattr(GameMaster, "ram_usage_mb")


class TestDataClasses:
    """Verify data classes work correctly."""

    def test_validation_result_valid(self) -> None:
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.retry_prompt is None

    def test_validation_result_invalid(self) -> None:
        result = ValidationResult(
            is_valid=False,
            errors=["Missing field: name"],
            retry_prompt="Fix the missing field.",
        )
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.retry_prompt is not None

    def test_consistency_report(self) -> None:
        report = ConsistencyReport(
            is_consistent=False,
            violations=["Chapter 2 mentions fire magic but Bible forbids it"],
            suggestions=["Replace with salt-binding magic"],
        )
        assert report.is_consistent is False
        assert len(report.violations) == 1
        assert len(report.suggestions) == 1

    def test_game_master_context(self) -> None:
        context = GameMasterContext(
            current_scene="The wind howls fiercely.",
            world_rules="Magic fails near running water.",
            relevant_lore=[
                {"name": "Salt Wraith", "summary": "An undead creature."}
            ],
            visited_nodes=["node_01", "node_02"],
            active_flags={"took_shard": True},
        )
        assert context.current_scene == "The wind howls fiercely."
        assert len(context.relevant_lore) == 1
        assert len(context.visited_nodes) == 2
        assert context.active_flags["took_shard"] is True


class TestBackendImports:
    """Verify backends are importable."""

    def test_llm_backend_imports(self) -> None:
        from src.backends import LlamaCppTextGenerator, LlamaCppValidator

        assert LlamaCppTextGenerator is not None
        assert LlamaCppValidator is not None

    def test_image_backend_imports(self) -> None:
        from src.backends import SDCppImageGenerator

        assert SDCppImageGenerator is not None

    def test_midi_backend_imports(self) -> None:
        from src.backends import AbcMusicGenerator

        assert AbcMusicGenerator is not None
