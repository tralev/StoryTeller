"""Phase 5.6D: Reproducibility semantics — deterministic run_id + archive-level SHA256 test.

Verifies:
  1. run_id is deterministic — same seed+config → same run_id
  2. Same seed twice → all content/* entries have identical SHA256
  3. Same seed twice → same content_hash in manifest
  4. Same seed twice → same story_id (deterministic UUID5)
  5. Different seeds → different content (negative control)
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from src.application.models import GenerationRequest

from .test_production_wiring import (
    InstrumentedGenerateStory,
    TrackedImageGenerator,
    TrackedMusicGenerator,
    TrackedTextGenerator,
    _clear_fakes,
    _inject_fakes,
)


# ── ZIP content hashing helpers ──────────────────────────────────────────────


def _canonical_zip_hashes(zip_path: Path) -> dict[str, str]:
    """Extract SHA256 of every entry in a .story ZIP.

    Returns {filename: sha256_hex} for all entries.
    Excludes manifest.json.meta.* fields from manifest hash comparison
    by pre-processing the manifest to remove operational fields.
    """
    hashes: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            data = zf.read(name)
            if name == "manifest.json":
                # Strip operational metadata before hashing
                manifest = json.loads(data)
                if "meta" in manifest:
                    # Keep only artifact_id (content-derived), remove rest
                    artifact_id = manifest.get("meta", {}).get("artifact_id", "")
                    manifest["meta"] = {"artifact_id": artifact_id}
                data = json.dumps(manifest, sort_keys=True).encode()
            hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def _all_content_entries(zip_path: Path) -> list[str]:
    """List all entries under content/ in a .story ZIP."""
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(n for n in zf.namelist() if n.startswith("content/"))


# ── Tests ────────────────────────────────────────────────────────────────────


class TestDeterministicRunId:
    """run_id is deterministic — seed+fingerprint derived."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
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
    async def test_same_seed_same_run_id(self, tmp_path: Path) -> None:
        """Two runs with same seed+config → same run_id in both manifests."""
        async def _run_and_get_run_id(suffix: str) -> str:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=42,
                title="Run ID Test",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"

            with zipfile.ZipFile(result.package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                return str(manifest["meta"]["run_id"])

        run_id_a = await _run_and_get_run_id("A")
        run_id_b = await _run_and_get_run_id("B")

        assert run_id_a == run_id_b, (
            f"run_id differs between runs: {run_id_a} vs {run_id_b}"
        )
        assert run_id_a.startswith("run_"), (
            f"run_id should start with 'run_', got {run_id_a}"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_different_seed_different_run_id(self, tmp_path: Path) -> None:
        """Different seeds → different run_ids."""
        async def _run_and_get_run_id(seed: int, suffix: str) -> str:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=seed,
                title="Run ID Test",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"

            with zipfile.ZipFile(result.package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                return str(manifest["meta"]["run_id"])

        run_id_42 = await _run_and_get_run_id(42, "A")
        run_id_99 = await _run_and_get_run_id(99, "B")

        assert run_id_42 != run_id_99, (
            f"Different seeds should produce different run_ids, "
            f"but both are {run_id_42}"
        )


class TestArchiveLevelDeterminism:
    """Byte-identical canonical content for same seed+config."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
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
    async def test_same_seed_same_archive_content(self, tmp_path: Path) -> None:
        """Same seed twice → all content/* SHA256 identical.

        This is the definitive reproducibility test — the strongest
        guarantee the pipeline can make without real models.
        """
        async def _run(seed: int, suffix: str) -> dict[str, str]:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=seed,
                title="Archive Determinism",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"
            return _canonical_zip_hashes(Path(result.package_path))

        hashes_a = await _run(42, "A")
        hashes_b = await _run(42, "B")

        # Every entry must be identical
        all_keys = set(hashes_a) | set(hashes_b)
        mismatches: list[str] = []
        for key in sorted(all_keys):
            if key not in hashes_a:
                mismatches.append(f"  {key}: missing in Run A")
            elif key not in hashes_b:
                mismatches.append(f"  {key}: missing in Run B")
            elif hashes_a[key] != hashes_b[key]:
                mismatches.append(
                    f"  {key}: {hashes_a[key][:16]}... vs {hashes_b[key][:16]}..."
                )

        assert not mismatches, (
            f"Archive-level determinism failure: {len(mismatches)} mismatch(es)\n"
            + "\n".join(mismatches)
        )

        # Verify content entries exist
        content_a = [k for k in hashes_a if k.startswith("content/")]
        assert len(content_a) >= 5, (
            f"Expected >=5 content entries, got {len(content_a)}: {content_a}"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_same_seed_same_content_hash(self, tmp_path: Path) -> None:
        """Same seed twice → same content_hash in manifest."""
        async def _get_content_hash(suffix: str) -> str:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=42,
                title="Content Hash Test",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"

            with zipfile.ZipFile(result.package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                return str(manifest["content_hash"])

        h_a = await _get_content_hash("A")
        h_b = await _get_content_hash("B")

        assert h_a == h_b, f"content_hash differs: {h_a[:16]}... vs {h_b[:16]}..."
        assert len(h_a) == 64, f"content_hash wrong length: {len(h_a)}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_same_seed_same_story_id(self, tmp_path: Path) -> None:
        """Same seed+title → same deterministic story_id (UUID5)."""
        async def _get_story_id(suffix: str) -> str:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=42,
                title="Same Title",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"

            with zipfile.ZipFile(result.package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                return str(manifest["story_id"])

        sid_a = await _get_story_id("A")
        sid_b = await _get_story_id("B")

        assert sid_a == sid_b, f"story_id differs: {sid_a} vs {sid_b}"
        # UUID format
        assert len(sid_a) == 36, f"story_id not UUID: {sid_a}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_different_seed_different_content(self, tmp_path: Path) -> None:
        """Different seeds → different archive content (negative control)."""
        async def _run(seed: int, suffix: str) -> dict[str, str]:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=seed,
                title="Diff Control",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"
            return _canonical_zip_hashes(Path(result.package_path))

        hashes_42 = await _run(42, "A")
        hashes_99 = await _run(99, "B")

        # At least one content entry should differ
        content_keys = [k for k in hashes_42 if k.startswith("content/")]
        differences = sum(
            1 for k in content_keys
            if hashes_42[k] != hashes_99.get(k, "")
        )
        assert differences >= 1, (
            f"Different seeds should produce different content, "
            f"but all {len(content_keys)} entries have identical hashes."
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_manifest_stripped_of_operational_metadata_identical(self, tmp_path: Path) -> None:
        """Same seed twice → manifest.json is identical after stripping meta.* operational fields."""
        async def _get_normalized_manifest(suffix: str) -> str:
            _clear_fakes()
            text = TrackedTextGenerator()
            image = TrackedImageGenerator()
            music = TrackedMusicGenerator()
            _inject_fakes(text, image, music)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=42,
                title="Manifest Norm",
                tone="dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"

            with zipfile.ZipFile(result.package_path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                # Normalize: strip operational fields
                if "meta" in manifest:
                    aid = manifest["meta"].get("artifact_id", "")
                    manifest["meta"] = {"artifact_id": aid}
                return json.dumps(manifest, sort_keys=True)

        norm_a = await _get_normalized_manifest("A")
        norm_b = await _get_normalized_manifest("B")

        assert norm_a == norm_b, (
            f"Normalized manifests differ:\n"
            f"  A: {norm_a[:80]}...\n"
            f"  B: {norm_b[:80]}..."
        )
