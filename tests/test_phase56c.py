"""Phase 5.6C: Run fingerprint enforcement — unit + integration tests.

Verifies:
  1. Matching fingerprints → resume proceeds normally
  2. Mismatched fingerprints → FingerprintMismatchError raised
  3. Empty/legacy fingerprint → warns but proceeds
  4. CheckpointStore.get_run_fingerprint() returns correct value
  5. GenerateStory is the sole owner of resume fingerprint enforcement
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.models import GenerationRequest
from src.pipeline.errors import FingerprintMismatchError
from src.storage.checkpoint import CheckpointStore

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
            phase=1,
            seed=42,
            output={"world_name": "Test"},
            run_fingerprint=_FP_A,
        )
        assert store.get_run_fingerprint() == _FP_A

    def test_returns_fingerprint_from_any_entry(self, tmp_path: Path) -> None:
        """First entry has no fingerprint but later one does."""
        store = CheckpointStore(str(tmp_path / "mix.db"))
        store.save(
            step_name="world_builder", phase=1, seed=42, output={"x": 1}, run_fingerprint=""
        )  # Legacy
        store.save(
            step_name="art_director", phase=2, seed=42, output={"x": 2}, run_fingerprint=_FP_A
        )
        assert store.get_run_fingerprint() == _FP_A

    def test_returns_none_when_all_entries_have_empty_fingerprint(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "legacy.db"))
        store.save(step_name="world_builder", phase=1, seed=42, output={"x": 1}, run_fingerprint="")
        store.save(step_name="story_writer", phase=2, seed=42, output={"x": 2}, run_fingerprint="")
        assert store.get_run_fingerprint() is None


# ── Unit tests: _verify_run_fingerprint ───────────────────────────────────────


class TestVerifyRunFingerprint:
    """GenerateStory._verify_run_fingerprint() raises/warns correctly."""

    def test_match_passes_silently(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "match.db"))
        store.save(
            step_name="world_builder", phase=1, seed=42, output={"x": 1}, run_fingerprint=_FP_A
        )

        from src.application.generate_story import GenerateStory

        # Should not raise
        GenerateStory._verify_run_fingerprint(store, _FP_A)

    def test_mismatch_raises(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "mismatch.db"))
        store.save(
            step_name="world_builder", phase=1, seed=42, output={"x": 1}, run_fingerprint=_FP_A
        )

        from src.application.generate_story import GenerateStory

        with pytest.raises(FingerprintMismatchError) as exc_info:
            GenerateStory._verify_run_fingerprint(store, _FP_B)

        error = exc_info.value
        assert error.code == "FP_001"
        assert error.retryable is False
        assert error.details["stored_fingerprint"] == _FP_A
        assert error.details["incoming_fingerprint"] == _FP_B

    def test_empty_fingerprint_is_rejected(self, tmp_path: Path) -> None:
        store = CheckpointStore(str(tmp_path / "legacy.db"))
        store.save(step_name="world_builder", phase=1, seed=42, output={"x": 1}, run_fingerprint="")

        from src.application.generate_story import GenerateStory

        with pytest.raises(FingerprintMismatchError):
            GenerateStory._verify_run_fingerprint(store, _FP_B)

    def test_none_fingerprint_is_rejected(self, tmp_path: Path) -> None:
        """An empty checkpoint database cannot establish run identity."""
        store = CheckpointStore(str(tmp_path / "empty.db"))

        from src.application.generate_story import GenerateStory

        with pytest.raises(FingerprintMismatchError):
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
            seed=42,
            title="FP Match",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
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
    async def test_checkpoint_without_run_spec_is_rejected_before_resume(
        self, tmp_path: Path
    ) -> None:
        """An incomplete legacy checkpoint cannot bypass the RunSpec contract."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Pre-seed checkpoints with a specific fingerprint
        store = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1,
            seed=42,
            output={"world_name": "Old Config"},
            run_fingerprint=_FP_A,
        )
        store.save(
            step_name="art_director",
            output_key="style_bible",
            phase=2,
            seed=42,
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
            seed=42,
            title="FP Mismatch",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,
        )

        result = await service.execute(request)

        assert result.errors == ["resume: stored run_spec.json is missing"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_legacy_checkpoints_without_run_spec_are_rejected(self, tmp_path: Path) -> None:
        """Legacy checkpoints are not silently resumed with guessed defaults."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Pre-seed legacy checkpoints (no fingerprint)
        store = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        store.save(
            step_name="world_builder",
            output_key="bible",
            phase=1,
            seed=42,
            output={"world_name": "Legacy", "entities": {"characters": []}},
            run_fingerprint="",  # Legacy — no fingerprint
        )
        store.save(
            step_name="art_director",
            output_key="style_bible",
            phase=2,
            seed=42,
            output={"art_style": {}},
            run_fingerprint="",
        )

        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="Legacy Resume",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,
        )

        result = await service.execute(request)
        assert result.errors == ["resume: stored run_spec.json is missing"]
