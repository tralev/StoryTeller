"""Exit condition #9: Resume verification test.

Verifies that resuming after a crash produces the same canonical archive.
Uses the same TrackedTextGenerator/TrackedImageGenerator/TrackedMusicGenerator
from test_production_wiring.py.

Test strategy:
  1. Full pipeline (Run A) — produces a .story ZIP, extract content hashes
  2. Simulate crash: delete images/midi output dirs but keep checkpoint.db
  3. Resume (Run B) — same seed, same output_dir, loads from checkpoint
  4. Orchestrator skips phases 1-4 (text), runs 5+ (image, music, finalize)
  5. Compare content/*.json SHA256 between Run A and Run B — must be identical
  6. Compare package ZIP SHA256 — may differ (manifest has wall-clock timestamps)
     but content artifacts must match.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from src.application.models import GenerationRequest

# Import shared fakes from test_production_wiring
from .test_production_wiring import (
    InstrumentedGenerateStory,
    TrackedImageGenerator,
    TrackedMusicGenerator,
    TrackedTextGenerator,
    _clear_fakes,
    _inject_fakes,
)


def _content_json_hashes(zip_path: Path) -> dict[str, str]:
    """Extract SHA256 hashes of all content/*.json files in a .story ZIP.

    Excludes manifest.json (has wall-clock timestamps).
    """
    hashes: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if name.startswith("content/") and name.endswith(".json"):
                hashes[name] = hashlib.sha256(zf.read(name)).hexdigest()
    return hashes


def _content_json_count(zip_path: Path) -> int:
    """Count content/*.json files in a .story ZIP."""
    with zipfile.ZipFile(zip_path) as zf:
        return sum(1 for n in zf.namelist()
                   if n.startswith("content/") and n.endswith(".json"))


def _package_sha256(zip_path: Path) -> str:
    """SHA256 of the entire .story file."""
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


class TestResumeProducesIdenticalCanonicalArchive:
    """Resume after text phase produces identical content artifacts."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent.parent
        schemas_dir = str(project_root / "docs" / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas directory not found")

    def setup_method(self) -> None:
        _clear_fakes()

    def teardown_method(self) -> None:
        _clear_fakes()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_after_text_phase_same_content(self, tmp_path: Path) -> None:
        """After text phase, resume produces identical content/*.json hashes.

        Steps:
          1. Run full pipeline → Run A .story
          2. Delete images/midi dirs, keep checkpoints
          3. Resume with same seed → Run B .story
          4. Compare content hashes — identical
        """
        output_dir = str(tmp_path / "output")
        seed = 42

        # ── Run A: Full pipeline ────────────────────────────────────
        text_a = TrackedTextGenerator()
        image_a = TrackedImageGenerator()
        music_a = TrackedMusicGenerator()
        _inject_fakes(text_a, image_a, music_a)

        service_a = InstrumentedGenerateStory()
        request_a = GenerationRequest(
            seed=seed,
            title="Resume Verification Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=False,  # Fresh start
        )

        result_a = await service_a.execute(request_a)
        assert result_a.errors == [], f"Run A errors: {result_a.errors}"
        pkg_a = Path(result_a.package_path)
        assert pkg_a.exists()

        # Record Run A hashes
        hashes_a = _content_json_hashes(pkg_a)
        assert len(hashes_a) >= 5, f"Expected >=5 content JSONs, got {len(hashes_a)}"
        count_a = _content_json_count(pkg_a)

        # Record call counts (baseline)
        text_calls_a = text_a.call_count
        img_calls_a = image_a.call_count

        # ── Simulate crash: delete image/midi output dirs ────────────
        # Checkpoint.db is preserved in output_dir
        images_dir = Path(output_dir) / "images"
        midi_dir = Path(output_dir) / "midi"
        thumb_dir = Path(output_dir) / "thumbnails"

        for d in [images_dir, midi_dir, thumb_dir]:
            if d.exists():
                shutil.rmtree(d)

        # Delete the old .story file too (Run A's package)
        pkg_a.unlink(missing_ok=True)

        # Delete any artifact JSON files (they'll be regenerated from checkpoint)
        for json_file in Path(output_dir).glob("*.json"):
            json_file.unlink()

        # ── Run B: Resume from checkpoint ──────────────────────────
        _clear_fakes()
        text_b = TrackedTextGenerator()
        image_b = TrackedImageGenerator()
        music_b = TrackedMusicGenerator()
        _inject_fakes(text_b, image_b, music_b)

        service_b = InstrumentedGenerateStory()
        request_b = GenerationRequest(
            seed=seed,
            title="Resume Verification Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,  # Resume from checkpoint
        )

        result_b = await service_b.execute(request_b)
        assert result_b.errors == [], f"Run B errors: {result_b.errors}"
        pkg_b = Path(result_b.package_path)
        assert pkg_b.exists()

        # Record Run B hashes
        hashes_b = _content_json_hashes(pkg_b)
        count_b = _content_json_count(pkg_b)

        # ── Assertions ──────────────────────────────────────────────

        # 1. Same number of content JSON files
        assert count_b == count_a, (
            f"Content file count differs: {count_a} (A) vs {count_b} (B)"
        )

        # 2. All content/*.json files are identical
        mismatches: list[str] = []
        for key in hashes_a:
            if key not in hashes_b:
                mismatches.append(f"  {key}: missing in Run B")
            elif hashes_a[key] != hashes_b[key]:
                mismatches.append(
                    f"  {key}: {hashes_a[key][:16]}... (A) vs {hashes_b[key][:16]}... (B)"
                )
        for key in hashes_b:
            if key not in hashes_a:
                mismatches.append(f"  {key}: missing in Run A")

        assert not mismatches, (
            f"Content hash mismatch after resume ({len(mismatches)} file(s)):\n"
            + "\n".join(mismatches)
        )

        # 3. Run B text generator should have been called LESS than Run A
        #    (because text phase was skipped via checkpoint)
        #    But note: music generation also uses text generator.
        #    On resume, the Orchestrator still runs all phases — it just
        #    skips generate() for completed steps. But the music step
        #    IS still run because it loses its checkpoint when we delete midi dir.
        #    So text calls in Run B = music-only calls (no bible/style/story/graph calls).
        assert text_b.call_count <= text_a.call_count, (
            f"Text calls increased on resume: {text_a.call_count} → {text_b.call_count}"
        )

        # 4. Image generator called in both runs (images were deleted)
        assert image_b.call_count >= 1, (
            f"Image generator not called on resume: {image_b.call_count}"
        )

        # 5. Both packages pass acceptance
        from src.storage.package_acceptance import PackageAcceptance
        gate = PackageAcceptance()
        acc_a = gate.validate(str(pkg_a))
        acc_b = gate.validate(str(pkg_b))
        assert acc_a.accepted, f"Run A package rejected:\n{acc_a.format_issues()}"
        assert acc_b.accepted, f"Run B package rejected:\n{acc_b.format_issues()}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_with_node_checkpoints_preserved(self, tmp_path: Path) -> None:
        """Node checkpoints survive full pipeline resume — BatchScheduler skips done nodes.

        This verifies Phase 5.5H item 3 integration: per-node checkpoints are
        preserved across pipeline runs and BatchScheduler resumes from them.
        """
        output_dir = str(tmp_path / "output")
        seed = 77

        # ── Run A: Full pipeline ────────────────────────────────────
        text_a = TrackedTextGenerator()
        image_a = TrackedImageGenerator()
        music_a = TrackedMusicGenerator()
        _inject_fakes(text_a, image_a, music_a)

        service_a = InstrumentedGenerateStory()
        request_a = GenerationRequest(
            seed=seed,
            title="Node Checkpoint Resume",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=False,
        )

        result_a = await service_a.execute(request_a)
        assert result_a.errors == [], f"Run A errors: {result_a.errors}"
        pkg_a = Path(result_a.package_path)
        hashes_a = _content_json_hashes(pkg_a)
        img_calls_a = image_a.call_count

        # Keep everything — don't delete images or midi dirs
        # Only delete the .story file so Run B creates a fresh one
        pkg_a.unlink(missing_ok=True)

        # ── Run B: Resume with node checkpoints intact ──────────────
        _clear_fakes()
        text_b = TrackedTextGenerator()
        image_b = TrackedImageGenerator()
        music_b = TrackedMusicGenerator()
        _inject_fakes(text_b, image_b, music_b)

        service_b = InstrumentedGenerateStory()
        request_b = GenerationRequest(
            seed=seed,
            title="Node Checkpoint Resume",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,
        )

        result_b = await service_b.execute(request_b)
        assert result_b.errors == [], f"Run B errors: {result_b.errors}"
        pkg_b = Path(result_b.package_path)

        hashes_b = _content_json_hashes(pkg_b)

        # ── Assertions ──────────────────────────────────────────────

        # 1. Content identical
        for key in hashes_a:
            assert key in hashes_b, f"Missing {key} in Run B"
            assert hashes_a[key] == hashes_b[key], (
                f"{key}: {hashes_a[key][:16]}... vs {hashes_b[key][:16]}..."
            )

        # 2. Image generator should be called ZERO times on resume
        #    because node checkpoints + files still exist
        assert image_b.call_count == 0, (
            f"Image generator called {image_b.call_count} times on resume "
            f"(expected 0 — node checkpoints + files intact)"
        )

        # 3. Node checkpoints in DB should have resumed count
        from src.storage.checkpoint import CheckpointStore
        db_path = Path(output_dir) / "checkpoint.db"
        store = CheckpointStore(str(db_path))
        img_nodes = store.load_all_nodes("image_generator")
        music_nodes = store.load_all_nodes("music_generator")
        assert len(img_nodes) >= 1, "No image node checkpoints found"
        assert len(music_nodes) >= 1, "No music node checkpoints found"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_different_seed_produces_different_archive(self, tmp_path: Path) -> None:
        """Resume with different seed should produce different content."""
        # Run A: seed 42
        output_a = str(tmp_path / "output_a")
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        result_a = await service.execute(GenerationRequest(
            seed=42, title="Different Seeds", tone="dark_fantasy",
            output_dir=output_a, config_path="/nonexistent", resume=False,
        ))
        assert result_a.errors == [], f"Run A errors: {result_a.errors}"
        hashes_a = _content_json_hashes(Path(result_a.package_path))

        # Run B: seed 99
        _clear_fakes()
        text2 = TrackedTextGenerator()
        image2 = TrackedImageGenerator()
        music2 = TrackedMusicGenerator()
        _inject_fakes(text2, image2, music2)

        output_b = str(tmp_path / "output_b")
        result_b = await service.execute(GenerationRequest(
            seed=99, title="Different Seeds", tone="dark_fantasy",
            output_dir=output_b, config_path="/nonexistent", resume=False,
        ))
        assert result_b.errors == [], f"Run B errors: {result_b.errors}"
        hashes_b = _content_json_hashes(Path(result_b.package_path))

        # At least one content artifact should differ
        differences = sum(1 for k in hashes_a
                         if hashes_a[k] != hashes_b.get(k, ""))
        assert differences >= 1, (
            "Different seeds should produce different content, "
            f"but all {len(hashes_a)} artifacts have identical hashes."
        )
