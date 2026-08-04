"""Tests for Phase 5.5 remaining gaps — verify, ModelConfig, KeyboardInterrupt."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest


class TestForgeVerify:
    """forge verify command integrates PackageAcceptance."""

    @pytest.mark.integration
    def test_verify_valid_story_passes(self, tmp_path: Path) -> None:
        """verify on a valid .story passes (minimal fixture)."""
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures" / "story_packages" / "minimal_valid_1_node.story"
        )
        if not fixture.exists():
            pytest.skip("minimal_valid_1_node.story not found")

        result = subprocess.run(
            [sys.executable, "-m", "src", "verify", str(fixture.resolve())],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert result.returncode == 0, (
            f"verify failed with exit {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )
        assert "SHA256:" in result.stdout
        assert "Package acceptance" in result.stdout

    @pytest.mark.integration
    def test_verify_invalid_story_fails(self, tmp_path: Path) -> None:
        """verify on an invalid .story rejects it."""
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures" / "story_packages" / "invalid_missing_manifest.story"
        )
        if not fixture.exists():
            pytest.skip("invalid_missing_manifest.story not found")

        result = subprocess.run(
            [sys.executable, "-m", "src", "verify", str(fixture.resolve())],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert result.returncode != 0, (
            f"verify should fail for invalid story, got exit {result.returncode}"
        )

    @pytest.mark.integration
    def test_verify_nonexistent_file_errors(self, tmp_path: Path) -> None:
        """verify on nonexistent file exits with error."""
        result = subprocess.run(
            [sys.executable, "-m", "src.cli", "verify", "/nonexistent/path.story"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert result.returncode == 1
        assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


class TestModelConfigValidation:
    """ModelConfig.from_dict warns on unrecognized fields."""

    def test_from_dict_warns_on_unknown_fields(self) -> None:
        """Image-specific fields like size/steps trigger a warning."""
        from src.config import ModelConfig
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ModelConfig.from_dict({
                "provider": "stable_diffusion_cpp",
                "model": "sdxl",
                "quantization": "Q8_0",
                "size": [512, 512],  # Not a ModelConfig field
                "steps": 20,          # Not a ModelConfig field
            })

        assert cfg.provider == "stable_diffusion_cpp"
        assert cfg.model == "sdxl"

        # Should have at least one warning about unrecognized fields
        field_warnings = [x for x in w if "ignoring unrecognized" in str(x.message).lower()]
        assert len(field_warnings) >= 1, (
            f"Expected warning about unrecognized fields, got {[str(x.message) for x in w]}"
        )

    def test_from_dict_only_known_fields_silent(self) -> None:
        """No warning when only known fields are passed."""
        from src.config import ModelConfig
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = ModelConfig.from_dict({
                "provider": "llama_cpp",
                "model": "qwen",
                "quantization": "Q4_K_M",
                "max_tokens": 4096,
                "temperature": 0.7,
            })

        assert cfg.provider == "llama_cpp"
        field_warnings = [x for x in w if "ignoring unrecognized" in str(x.message).lower()]
        assert len(field_warnings) == 0, (
            f"Expected no warnings, got {[str(x.message) for x in w]}"
        )


class TestKeyboardInterruptHandling:
    """ModelManager.resource_scope handles KeyboardInterrupt gracefully."""

    @pytest.mark.asyncio
    async def test_resource_scope_handles_keyboard_interrupt(self) -> None:
        """resource_scope catches KeyboardInterrupt, unloads, re-raises."""
        from src.backends.model_manager import ModelManager, ModelRole

        load_count = 0
        unload_count = 0

        class TestBackend:
            provider = "test"
            async def load(self) -> None:
                nonlocal load_count
                load_count += 1
            async def unload(self) -> None:
                nonlocal unload_count
                unload_count += 1

        manager = ModelManager(budget_mb=10240)
        manager.register("test", TestBackend(), role=ModelRole.TEXT, ram_mb=100)

        with pytest.raises(KeyboardInterrupt):
            async with manager.resource_scope("test"):
                raise KeyboardInterrupt()

        # Model should be loaded then unloaded
        assert load_count == 1, f"Expected 1 load, got {load_count}"
        assert unload_count == 1, f"Expected 1 unload, got {unload_count}"

    @pytest.mark.asyncio
    async def test_resource_scope_unloads_on_regular_exception(self) -> None:
        """resource_scope unloads even on regular exceptions."""
        from src.backends.model_manager import ModelManager, ModelRole

        load_count = 0
        unload_count = 0

        class TestBackend:
            provider = "test"
            async def load(self) -> None:
                nonlocal load_count
                load_count += 1
            async def unload(self) -> None:
                nonlocal unload_count
                unload_count += 1

        manager = ModelManager(budget_mb=10240)
        manager.register("test", TestBackend(), role=ModelRole.TEXT, ram_mb=100)

        with pytest.raises(ValueError, match="test error"):
            async with manager.resource_scope("test"):
                raise ValueError("test error")

        assert load_count == 1
        assert unload_count == 1


class TestConfigModelsYaml:
    """config/models.yaml is consistent with actual model files."""

    def test_yaml_model_names_match_actual_files(self) -> None:
        """The models.yaml references filenames that exist in ai_models/."""
        import yaml
        config_path = Path(__file__).resolve().parent.parent / "config" / "models.yaml"
        if not config_path.exists():
            pytest.skip("models.yaml not found")

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        ai_models = Path(__file__).resolve().parent.parent / "ai_models"

        generators = raw.get("generators", {})
        for role in ["text", "validator", "image", "game_master"]:
            gen = generators.get(role, {})
            filename = gen.get("file", "")
            if not filename:
                continue

            model_path = ai_models / filename
            assert model_path.exists(), (
                f"Config references '{filename}' for {role} but file not found at {model_path}. "
                f"Available models: {[f.name for f in ai_models.glob('*.gguf')]}"
            )
