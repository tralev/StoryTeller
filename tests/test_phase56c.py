"""Phase 5.6C: Run fingerprint enforcement — unit + integration tests.

Verifies:
  1. Matching fingerprints → resume proceeds normally
  2. Mismatched fingerprints → FingerprintMismatchError raised
  3. Empty/legacy fingerprint → warns but proceeds
  4. CheckpointStore.get_run_fingerprint() returns correct value
  5. Orchestrator fingerprint comparison on resume
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.application.models import GenerationRequest
from src.storage.checkpoint import CheckpointStore
from src.pipeline.errors import FingerprintMismatchError

from .test_production_wiring import (
    InstrumentedGenerateStory,
    TrackedImageGenerator,
    TrackedMusicGenerator,
    TrackedTextGenerator,
    _clear_fakes,
    _inject_fakes,
)

# ── shared test fingerprint ──────────────────────────────────────────────────
_FP_A = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
_FP_B = "bbbbbb1234567890bbbbbb1234567890bbbbbb1234567890bbbbbb1234567890"


# ── Unit tests: CheckpointStore.get_run_fingerprint ───────────────────────────


class TestGetRunFingerprint:
    """CheckpointStore.get_run_fingerprint() returns correct fingerprint."""

    def test_returns_none_for_empty_db(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "empty.db"))
        assert store.get_run_fingerprint() is None

    def test_returns_stored_fingerprint(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "test.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Test"},
            run_fingerprint=_FP_A,
        )
        assert store.get_run_fingerprint() == _FP_A

    def test_returns_fingerprint_from_any_entry(self, tmp_path: Path) -> None:
        """First entry has no fingerprint but later one does."""
        store = CheckpointStore(str(tmp_path / "mix.db"))
        store.save(step_name="world_builder", phase=1, seed=42,
                   output={"x": 1}, run_fingerprint="")  # Legacy
        store.save(step_name="art_director", phase=2, seed=42,
                   output={"x": 2}, run_fingerprint=_FP_A)
        assert store.get_run_fingerprint() == _FP_A

    def test_returns_none_when_all_entries_have_empty_fingerprint(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "legacy.db"))
        store.save(step_name="world_builder", phase=1, seed=42,
                   output={"x": 1}, run_fingerprint="")
        store.save(step_name="story_writer", phase=2, seed=42,
                   output={"x": 2}, run_fingerprint="")
        assert store.get_run_fingerprint() is None


# ── Unit tests: _verify_run_fingerprint ───────────────────────────────────────


class TestVerifyRunFingerprint:
    """GenerateStory._verify_run_fingerprint() raises/warns correctly."""

    def test_match_passes_silently(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "match.db"))
        store.save(step_name="world_builder", phase=1, seed=42,
                   output={"x": 1}, run_fingerprint=_FP_A)

        from src.application.generate_story import GenerateStory
        # Should not raise
        GenerateStory._verify_run_fingerprint(store, _FP_A)

    def test_mismatch_raises(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "mismatch.db"))
        store.save(step_name="world_builder", phase=1, seed=42,
                   output={"x": 1}, run_fingerprint=_FP_A)

        from src.application.generate_story import GenerateStory
        with pytest.raises(FingerprintMismatchError) as exc_info:
            GenerateStory._verify_run_fingerprint(store, _FP_B)

        error = exc_info.value
        assert error.code == "FP_001"
        assert error.retryable is False
        assert error.details["stored_fingerprint"] == _FP_A
        assert error.details["incoming_fingerprint"] == _FP_B

    def test_empty_fingerprint_warns_but_passes(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "legacy.db"))
        store.save(step_name="world_builder", phase=1, seed=42,
                   output={"x": 1}, run_fingerprint="")

        from src.application.generate_story import GenerateStory
        with pytest.warns(UserWarning, match="no stored run fingerprint"):
            GenerateStory._verify_run_fingerprint(store, _FP_B)

    def test_none_fingerprint_warns_but_passes(self, tmp_path: Path) -> None:
        """Empty DB returns None — warn but proceed."""
        store = CheckpointStore(str(tmp_path / "empty.db"))

        from src.application.generate_story import GenerateStory
        with pytest.warns(UserWarning, match="no stored run fingerprint"):
            GenerateStory._verify_run_fingerprint(store, _FP_B)


# ── Unit tests: FingerprintMismatchError ──────────────────────────────────────


class TestFingerprintMismatchError:
    """FingerprintMismatchError has correct properties."""

    def test_is_terminal_not_retryable(self) -> None:
        from src.pipeline.errors import is_retryable, is_terminal
        error = FingerprintMismatchError(_FP_A, _FP_B)
        assert not is_retryable(error)
        assert is_terminal(error)

    def test_message_includes_fingerprint_prefixes(self) -> None:
        error = FingerprintMismatchError(_FP_A, _FP_B)
        msg = str(error)
        assert _FP_A[:16] in msg
        assert _FP_B[:16] in msg
        assert "no-resume" in msg or "start fresh" in msg


# ── Integration tests: fingerprint enforcement in GenerateStory ───────────────


class TestFingerprintEnforcementInPipeline:
    """Full pipeline tests that verify fingerprint enforcement."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas directory not found")

    def setup_method(self) -> None:
        _clear_fakes()

    def teardown_method(self) -> None:
        _clear_fakes()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_matching_fingerprints_resume_succeeds(self, tmp_path: Path) -> None:
        """Resume with same config → works normally."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # ── Run A: Create checkpoints with fingerprint ──
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42, title="FP Match", tone="dark_fantasy",
            output_dir=output_dir, config_path="/nonexistent",
            resume=True,
        )
        result = await service.execute(request)
        assert result.errors == [], f"Run A errors: {result.errors}"

        # Verify fingerprint was stored
        store = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        fp = store.get_run_fingerprint()
        assert fp is not None
        assert len(fp) == 64, f"Fingerprint not 64 chars: {len(fp)}"

        # ── Run B: Resume (same config, no model changes) ──
        _clear_fakes()
        text2 = TrackedTextGenerator()
        image2 = TrackedImageGenerator()
        music2 = TrackedMusicGenerator()
        _inject_fakes(text2, image2, music2)

        result2 = await service.execute(request)
        assert result2.errors == [], f"Resume errors: {result2.errors}"
        assert result2.package_path

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mismatched_fingerprints_raise_on_resume(self, tmp_path: Path) -> None:
        """Resume with different config → FingerprintMismatchError."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Pre-seed checkpoints with a specific fingerprint
        store = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Old Config"},
            run_fingerprint=_FP_A,
        )
        store.save(
            step_name="art_director",
            output_key="style_bible",
            phase=2, seed=42,
            output={"art_style": {}},
            run_fingerprint=_FP_A,
        )

        # Now run with a different config — should get FingerprintMismatchError
        # Override _compute_run_fingerprint to return a different FP
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        # Create a subclass that forces a different fingerprint
        class MismatchedService(InstrumentedGenerateStory):
            @staticmethod
            def _compute_run_fingerprint(config: Any, out: Any) -> str:
                return _FP_B  # Different from stored _FP_A

        service = MismatchedService()
        request = GenerationRequest(
            seed=42, title="FP Mismatch", tone="dark_fantasy",
            output_dir=output_dir, config_path="/nonexistent",
            resume=True,
        )

        result = await service.execute(request)

        # Should have a fingerprint mismatch error
        assert len(result.errors) >= 1, f"Expected errors, got: {result.errors}"
        assert any(
            "fingerprint mismatch" in e.lower() for e in result.errors
        ), f"Expected fingerprint mismatch, got: {result.errors}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_legacy_checkpoints_warn_but_proceed(self, tmp_path: Path) -> None:
        """Legacy checkpoint (no fingerprint) warns but completes."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Pre-seed legacy checkpoints (no fingerprint)
        store = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Legacy", "entities": {"characters": []}},
            run_fingerprint="",  # Legacy — no fingerprint
        )
        store.save(
            step_name="art_director",
            output_key="style_bible",
            phase=2, seed=42,
            output={"art_style": {}},
            run_fingerprint="",
        )

        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42, title="Legacy Resume", tone="dark_fantasy",
            output_dir=output_dir, config_path="/nonexistent",
            resume=True,
        )

        with pytest.warns(UserWarning, match="no stored run fingerprint"):
            result = await service.execute(request)

        # Should complete normally (legacy path)
        assert result.errors == [], f"Legacy resume errors: {result.errors}"
        assert result.package_path


# ── Unit tests: Orchestrator fingerprint enforcement ──────────────────────────


class TestOrchestratorFingerprint:
    """Orchestrator.run() enforces fingerprint match on resume."""

    def test_orchestrator_mismatch_raises(self, tmp_path: Path) -> None:
        """Different fingerprint → FingerprintMismatchError."""
        from src.job_queue import PipelineContext
        from src.storage.orchestrator import Orchestrator

        # Pre-seed checkpoint
        store = CheckpointStore(str(tmp_path / "orch.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Old"},
            run_fingerprint=_FP_A,
        )

        orch = Orchestrator(store, {})
        orch.run_fingerprint = _FP_B  # Different!

        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))

        import asyncio
        with pytest.raises(FingerprintMismatchError):
            asyncio.run(orch.run(ctx))

    def test_orchestrator_match_proceeds(self, tmp_path: Path) -> None:
        """Same fingerprint → no error (just completes or fails on missing steps)."""
        from src.job_queue import PipelineContext
        from src.storage.orchestrator import Orchestrator

        store = CheckpointStore(str(tmp_path / "orch_match.db"))
        # No checkpoints — starts at phase 1, no fingerprint check needed
        orch = Orchestrator(store, {})
        orch.run_fingerprint = _FP_A

        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))

        import asyncio
        # Should fail on missing step, NOT on fingerprint
        with pytest.raises(ValueError, match="Unknown step"):
            asyncio.run(orch.run(ctx))

    def test_orchestrator_legacy_warns(self, tmp_path: Path) -> None:
        """Legacy checkpoints → warns but runs."""
        from src.job_queue import PipelineContext
        from src.storage.orchestrator import Orchestrator

        store = CheckpointStore(str(tmp_path / "orch_legacy.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Legacy"},
            run_fingerprint="",
        )
        store.save(
            step_name="art_director",
            output_key="style_bible",
            phase=2, seed=42,
            output={"art_style": {}},
            run_fingerprint="",
        )

        orch = Orchestrator(store, {})
        orch.run_fingerprint = _FP_A

        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))

        import asyncio
        with pytest.warns(UserWarning, match="no stored run fingerprint"):
            # Should skip to phase 3 then fail on missing step (not fingerprint)
            with pytest.raises(ValueError, match="Unknown step"):
                asyncio.run(orch.run(ctx))
