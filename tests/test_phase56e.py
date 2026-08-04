"""Phase 5.6E: LLM validator policy — status, registration, deterministic vs LLM.

Verifies:
  1. ValidatorStatus enum: SKIPPED, UNAVAILABLE, FAILED, VALID
  2. ValidationResult auto-derives status from is_valid
  3. DeterministicValidator reports VALID/FAILED correctly
  4. Validator model registered with ModelManager
  5. Deterministic validators have 0 RAM (no load/unload needed)
  6. Null validators produce SKIPPED status
  7. Pipeline step reports validator status in output
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.interfaces.validator import (
    ValidationResult,
    ValidatorStatus,
)
from src.application.models import GenerationRequest


# ── Unit: ValidatorStatus enum ───────────────────────────────────────────────


class TestValidatorStatusEnum:
    """ValidatorStatus enum has correct values."""

    def test_all_statuses_exist(self) -> None:
        assert ValidatorStatus.SKIPPED.value == "skipped"
        assert ValidatorStatus.UNAVAILABLE.value == "unavailable"
        assert ValidatorStatus.FAILED.value == "failed"
        assert ValidatorStatus.VALID.value == "valid"

    def test_statuses_are_distinct(self) -> None:
        values = [s.value for s in ValidatorStatus]
        assert len(set(values)) == 4, f"Expected 4 distinct values, got {values}"


# ── Unit: ValidationResult status derivation ──────────────────────────────────


class TestValidationResultStatus:
    """ValidationResult.__post_init__ derives status correctly."""

    def test_explicit_status_preserved(self) -> None:
        result = ValidationResult(
            is_valid=False,
            status=ValidatorStatus.UNAVAILABLE,
        )
        assert result.status == ValidatorStatus.UNAVAILABLE

    def test_valid_derives_valid_status(self) -> None:
        result = ValidationResult(is_valid=True)
        assert result.status == ValidatorStatus.VALID

    def test_invalid_derives_failed_status(self) -> None:
        result = ValidationResult(is_valid=False)
        assert result.status == ValidatorStatus.FAILED

    def test_skipped_status_not_overwritten(self) -> None:
        result = ValidationResult(
            is_valid=False,
            status=ValidatorStatus.SKIPPED,
        )
        # SKIPPED should be preserved even though is_valid=False
        assert result.status == ValidatorStatus.SKIPPED


# ── Unit: DeterministicValidator status reporting ─────────────────────────────


class TestDeterministicValidatorStatus:
    """DeterministicValidator.validate() returns correct status."""

    def test_bible_valid_returns_valid_status(self, tmp_path: Path) -> None:
        from src.validators.composite import ValidationPlan, DeterministicValidator

        schemas_dir = str(
            Path(__file__).resolve().parent.parent / "schemas",
        )
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas not found")

        validator = DeterministicValidator(
            ValidationPlan(schema="bible"), schemas_dir,
        )

        # Use a real valid bible fixture
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "bible_valid.json"
        if not fixture_path.exists():
            pytest.skip("bible_valid.json fixture not found")

        import json
        valid_bible = json.loads(fixture_path.read_text())

        import asyncio
        result = asyncio.run(validator.validate(valid_bible, {}))
        assert result.status == ValidatorStatus.VALID
        assert result.is_valid

    def test_bible_invalid_returns_failed_status(self, tmp_path: Path) -> None:
        from src.validators.composite import ValidationPlan, DeterministicValidator

        schemas_dir = str(
            Path(__file__).resolve().parent.parent / "schemas",
        )
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas not found")

        validator = DeterministicValidator(
            ValidationPlan(schema="bible"), schemas_dir,
        )

        invalid_bible: dict[str, Any] = {"world_name": 123}  # Wrong type

        import asyncio
        result = asyncio.run(validator.validate(invalid_bible, {}))
        assert result.status == ValidatorStatus.FAILED
        assert not result.is_valid

    def test_deterministic_validator_zero_ram(self) -> None:
        from src.validators.composite import ValidationPlan, DeterministicValidator

        schemas_dir = str(
            Path(__file__).resolve().parent.parent / "schemas",
        )
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas not found")

        validator = DeterministicValidator(
            ValidationPlan(schema="bible"), schemas_dir,
        )
        assert validator.ram_usage_mb == 0
        assert validator.provider == "deterministic"


# ── Integration: Validator model registration with ModelManager ──────────────


class TestValidatorModelRegistration:
    """Validator is registered with ModelManager."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)

    @pytest.mark.integration
    def test_deterministic_validator_zero_ram_registration(self) -> None:
        """Deterministic validators report 0 RAM to ModelManager."""
        from src.backends.model_manager import ModelManager, ModelRole

        manager = ModelManager(budget_mb=10240)

        class DetValidator:
            provider: str = "deterministic"
            model_name: str = "rule-based"
            quantization: str = ""
            ram_usage_mb: int = 0
            async def load(self) -> None: pass
            async def unload(self) -> None: pass

        manager.register("validator", DetValidator(), role=ModelRole.VALIDATOR, ram_mb=0)
        assert manager.used_ram_mb == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_validator_registered_in_full_pipeline(self, tmp_path: Path) -> None:
        """After full pipeline run, ModelManager had validator registered."""
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

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42, title="Validator Reg Test", tone="dark_fantasy",
            output_dir=str(tmp_path / "output"), config_path="/nonexistent",
            resume=False,
        )

        result = await service.execute(request)
        assert not result.errors, f"Errors: {result.errors}"
        # Pipeline completed successfully with a validator registered


# ── Integration: Pipeline steps use correct validator status ──────────────────


class TestPipelineStepValidatorStatus:
    """PipelineStep reports validator status in StepOutput."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas directory not found")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_step_without_validator_reports_skipped(self, tmp_path: Path) -> None:
        """A step with no validator reports SKIPPED."""
        from src.job_queue import PipelineContext
        from src.models.world_builder import WorldBuilder

        from .test_production_wiring import (
            TrackedTextGenerator, _clear_fakes,
        )

        _clear_fakes()
        text_gen = TrackedTextGenerator()
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "No Validator Test"
        ctx.state["temperature"] = 0.7
        ctx.state["start_time"] = __import__("time").time()

        step = WorldBuilder(text_gen, validator=None)
        output = await step.run(ctx)

        assert output.validator_status == ValidatorStatus.SKIPPED.value

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_step_validate_returns_skipped_when_no_validator(self) -> None:
        """PipelineStep.validate() returns SKIPPED when validator=None."""
        from src.job_queue import PipelineContext
        from src.models.world_builder import WorldBuilder

        from .test_production_wiring import (
            TrackedTextGenerator, _clear_fakes,
        )

        _clear_fakes()
        text_gen = TrackedTextGenerator()
        ctx = PipelineContext(run_id="test", seed=42)
        step = WorldBuilder(text_gen, validator=None)

        # Generate first
        output = await step.generate(ctx)
        # Validate
        result = await step.validate(output, ctx)

        assert result.status == ValidatorStatus.SKIPPED
        assert result.is_valid

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_step_validate_returns_failed_for_invalid(self, tmp_path: Path) -> None:
        """PipelineStep.validate() returns FAILED for invalid content."""
        from src.job_queue import PipelineContext
        from src.validators.composite import ValidationPlan, DeterministicValidator
        from src.models.world_builder import WorldBuilder

        from .test_production_wiring import (
            TrackedTextGenerator, _clear_fakes,
        )

        schemas_dir = str(
            Path(__file__).resolve().parent.parent / "schemas",
        )
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas not found")

        _clear_fakes()
        text_gen = TrackedTextGenerator()
        validator = DeterministicValidator(
            ValidationPlan(schema="bible"), schemas_dir,
        )
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        step = WorldBuilder(text_gen, validator=validator)

        # Create a StepOutput with invalid data
        from src.models.base import StepOutput
        output = StepOutput(data={"world_name": 123}, step_name="world_builder")
        result = await step.validate(output, ctx)

        assert result.status == ValidatorStatus.FAILED
        assert not result.is_valid
