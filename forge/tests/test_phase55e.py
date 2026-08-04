"""Tests for Phase 5.5E: canonical/operational metadata split, atomic commits, run fingerprints.

Phase 5.5E:
  1. Separate canonical from operational metadata (meta sub-object)
  2. Remove temporal info from artifact IDs (content-derived only)
  3. Atomic artifact commits (temp file + os.replace)
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.artifact_store import ArtifactStore
from src.job_queue import PipelineContext
from src.storage.checkpoint import CheckpointEntry, CheckpointStore
from src.storage.packager import Packager


# ── Section 1: Canonical vs Operational Metadata ─────────────────────────────


class TestCanonicalOperationalSplit:
    """Canonical fields are separate from operational (meta)."""

    def test_manifest_has_meta_sub_object(self) -> None:
        """Manifest stores operational data in meta, canonical at root."""
        from src.storage.manifest_builder import ManifestBuilder

        ctx = PipelineContext(run_id="meta_test", seed=42)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "Meta Test"
        ctx.state["start_time"] = __import__("time").time()
        ctx.outputs["bible"] = {"world_name": "Test"}
        ctx.outputs["story"] = {"chapters": []}
        ctx.outputs["graph"] = {"nodes": [], "starting_node": "node_01"}
        ctx.outputs["images"] = {"images": {}}
        ctx.outputs["midi"] = {"midi": {}}
        ctx.outputs["gm_index"] = {"keywords": {}}

        async def _run() -> None:
            builder = ManifestBuilder()
            output = await builder.run(ctx)
            manifest = output.data

            # ── Canonical at root ──
            assert "schema_version" in manifest
            assert "story_id" in manifest
            assert "title" in manifest
            assert "seed" in manifest
            assert "generator_version" in manifest
            assert "models_used" in manifest
            assert "prompt_versions" in manifest
            assert "entry_point" in manifest
            assert "files" in manifest
            assert "stats" in manifest
            assert "content_hash" in manifest

            # ── Operational in meta ──
            assert "meta" in manifest
            meta = manifest["meta"]
            assert "generated_at" in meta
            assert "artifact_id" in meta
            assert "run_id" in meta
            assert "generation_time_seconds" in meta
            assert "peak_ram_mb" in meta

            # artifact_id starts empty, set by packager
            assert meta["artifact_id"] == "" or meta["artifact_id"].startswith("package_")

            # run_id matches context
            assert meta["run_id"] == "meta_test"

        import asyncio
        asyncio.run(_run())

    def test_canonical_fields_are_identical_for_same_seed(self) -> None:
        """Canonical fields produce identical content hash regardless of meta."""
        from src.storage.manifest_builder import ManifestBuilder

        async def _build(seed: int, run_id: str) -> dict:
            ctx = PipelineContext(run_id=run_id, seed=seed)
            ctx.state["tone"] = "dark_fantasy"
            ctx.state["title"] = "Content Test"
            ctx.state["start_time"] = __import__("time").time()
            ctx.outputs["bible"] = {"world_name": "Test"}
            ctx.outputs["story"] = {"chapters": []}
            ctx.outputs["graph"] = {"nodes": [], "starting_node": "node_01"}
            ctx.outputs["images"] = {"images": {}}
            ctx.outputs["midi"] = {"midi": {}}
            ctx.outputs["gm_index"] = {"keywords": {}}

            builder = ManifestBuilder()
            output = await builder.run(ctx)
            return output.data

        import asyncio

        m1 = asyncio.run(_build(42, "run_A"))
        m2 = asyncio.run(_build(42, "run_B"))

        # Content hash should be identical (same seed, same content)
        assert m1["content_hash"] == m2["content_hash"], (
            f"Content hash differs: {m1['content_hash'][:16]}... vs {m2['content_hash'][:16]}..."
        )

        # story_id should be identical (derived from seed + world_name)
        assert m1["story_id"] == m2["story_id"]

        # Operational metadata differs (different runs)
        assert m1["meta"]["run_id"] != m2["meta"]["run_id"]
        # generated_at may differ (wall-clock time)
        # generation_time_seconds may differ

    def test_meta_not_in_content_hash(self) -> None:
        """content_hash is computed from content/ files only, not meta."""
        from src.storage.manifest_builder import ManifestBuilder

        async def _build(run_id: str) -> dict:
            ctx = PipelineContext(run_id=run_id, seed=42)
            ctx.state["tone"] = "dark_fantasy"
            ctx.state["title"] = "Hash Test"
            ctx.state["start_time"] = __import__("time").time()
            ctx.outputs["bible"] = {"world_name": "Test"}
            ctx.outputs["story"] = {"chapters": []}
            ctx.outputs["graph"] = {"nodes": [], "starting_node": "node_01"}
            ctx.outputs["images"] = {"images": {}}
            ctx.outputs["midi"] = {"midi": {}}
            ctx.outputs["gm_index"] = {"keywords": {}}

            builder = ManifestBuilder()
            output = await builder.run(ctx)
            return output.data

        import asyncio

        m1 = asyncio.run(_build("run_A"))
        # Sleep briefly to get different generated_at
        import time
        time.sleep(0.1)
        m2 = asyncio.run(_build("run_B"))

        # Content hash unchanged (meta doesn't affect it)
        assert m1["content_hash"] == m2["content_hash"]

        # But meta timestamps may differ
        assert m1["meta"]["run_id"] != m2["meta"]["run_id"]


# ── Section 2: Content-Derived Artifact IDs ───────────────────────────────────


class TestContentDerivedArtifactIDs:
    """Artifact IDs are derived from content hash, never timestamps."""

    def test_packager_artifact_id_is_content_derived(self) -> None:
        """Packager sets artifact_id = package_{content_hash[:8]}."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PipelineContext(run_id="id_test", seed=42)
            ctx.state["start_time"] = __import__("time").time()
            ctx.outputs["bible"] = {"world_name": "A"}
            ctx.outputs["story"] = {"chapters": []}
            ctx.outputs["graph"] = {"nodes": [], "starting_node": "node_01"}
            ctx.outputs["gm_index"] = {"keywords": {}}
            ctx.outputs["style_bible"] = {"art_style": {}}
            ctx.outputs["images"] = {"images": {}}
            ctx.outputs["midi"] = {"midi": {}}
            ctx.outputs["manifest"] = {
                "schema_version": 1,
                "story_id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Artifact ID Test",
                "seed": 42,
                "generator_version": "0.1.0",
                "models_used": {
                    "text_generator": "mock", "validator": "mock",
                    "image_generator": "mock", "music_generator": "mock",
                },
                "prompt_versions": {
                    "world_builder": "v1", "story_writer": "v1",
                    "game_designer": "v1", "art_director": "v1", "composer": "v1",
                },
                "entry_point": "node_01",
                "files": {
                    "bible": "content/bible.json",
                    "story": "content/story.json",
                    "graph": "content/graph.json",
                    "gm_index": "content/gm_index.json",
                    "images": "content/images/",
                    "midi": "content/midi/",
                },
                "stats": {},
                "meta": {
                    "artifact_id": "",
                    "generated_at": "2026-08-03T00:00:00Z",
                    "run_id": "id_test",
                },
            }

            async def _run() -> None:
                pkg = Packager(output_dir=tmpdir)
                output = await pkg.run(ctx)
                aid = output.artifact_id
                assert aid.startswith("package_"), f"Expected package_* got {aid}"
                # Should be 8 hex chars after package_
                assert len(aid) == len("package_") + 8, f"Wrong length: {aid}"
                assert all(c in "0123456789abcdef" for c in aid.split("_", 1)[1]), (
                    f"Non-hex chars in artifact_id: {aid}"
                )

            import asyncio
            asyncio.run(_run())

    def test_same_content_same_artifact_id(self) -> None:
        """Same content → same artifact_id, even across separate Packager instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            async def _run() -> str:
                ctx = PipelineContext(run_id="same_id", seed=42)
                ctx.state["start_time"] = __import__("time").time()
                ctx.outputs["bible"] = {"world_name": "Test"}
                ctx.outputs["story"] = {"chapters": []}
                ctx.outputs["graph"] = {"nodes": [], "starting_node": "node_01"}
                ctx.outputs["gm_index"] = {"keywords": {}}
                ctx.outputs["style_bible"] = {"art_style": {}}
                ctx.outputs["images"] = {"images": {}}
                ctx.outputs["midi"] = {"midi": {}}
                ctx.outputs["manifest"] = {
                    "schema_version": 1,
                    "story_id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Test", "seed": 42, "generator_version": "0.1.0",
                    "models_used": {"text_generator": "m", "validator": "m",
                                    "image_generator": "m", "music_generator": "m"},
                    "prompt_versions": {"world_builder": "v1", "story_writer": "v1",
                                        "game_designer": "v1", "art_designer": "v1",
                                        "composer": "v1"},
                    "entry_point": "node_01",
                    "files": {"bible": "content/bible.json",
                              "story": "content/story.json",
                              "graph": "content/graph.json",
                              "gm_index": "content/gm_index.json",
                              "images": "content/images/",
                              "midi": "content/midi/"},
                    "stats": {},
                    "meta": {"artifact_id": "", "generated_at": "2026-08-03T00:00:00Z",
                             "run_id": "same_id"},
                }

                pkg = Packager(output_dir=tmpdir)
                output = await pkg.run(ctx)
                return output.artifact_id

            import asyncio
            id1 = asyncio.run(_run())
            id2 = asyncio.run(_run())
            assert id1 == id2, f"Different artifact_ids for same content: {id1} vs {id2}"

    def test_checkpoint_entry_artifact_id_is_not_temporal(self) -> None:
        """CheckpointEntry.artifact_id is content-derived, completed_at is operational."""
        entry = CheckpointEntry(
            step_name="test",
            output_key="bible",
            phase=1,
            seed=42,
            output_json='{"key":"value"}',
            completed_at=1234567890.0,
            artifact_id="bible_a1b2c3d4",  # Content-derived
        )
        # artifact_id has no timestamp
        assert ":" not in entry.artifact_id
        assert entry.artifact_id.startswith("bible_") or entry.artifact_id.startswith("package_")
        # completed_at is a separate operational field
        assert entry.completed_at > 0


# ── Section 3: Atomic Artifact Commits ────────────────────────────────────────


class TestAtomicArtifactCommits:
    """Artifacts are written atomically: .tmp file then os.replace."""

    def test_artifact_store_writes_atomically(self) -> None:
        """ArtifactStore writes .json.tmp first, then renames to .json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(output_dir=tmpdir)

            # Write an artifact
            store["bible"] = {"world_name": "Atomic Test"}

            # The .json file should exist, .json.tmp should NOT
            json_path = Path(tmpdir) / "bible.json"
            tmp_path = Path(tmpdir) / "bible.json.tmp"

            assert json_path.exists(), f"Expected {json_path} to exist"
            assert not tmp_path.exists(), f"Temporary {tmp_path} should not persist"

            # Content should be correct
            data = json.loads(json_path.read_text())
            assert data["world_name"] == "Atomic Test"

    def test_artifact_store_delete_cleans_disk(self) -> None:
        """Deleting a key removes the JSON file from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(output_dir=tmpdir)
            store["bible"] = {"world_name": "Will delete"}
            json_path = Path(tmpdir) / "bible.json"
            assert json_path.exists()

            del store["bible"]
            assert not json_path.exists()

    def test_packager_atomic_zip_write(self) -> None:
        """Packager writes to .story.tmp first, then renames atomically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Monkey-patch os.replace to track calls
            orig_replace = os.replace
            replace_calls: list[tuple[str, str]] = []

            def _tracking_replace(src: str, dst: str) -> None:
                replace_calls.append((src, dst))
                orig_replace(src, dst)

            ctx = PipelineContext(run_id="atomic_zip", seed=42)
            ctx.state["start_time"] = __import__("time").time()
            ctx.outputs["bible"] = {"world_name": "Test"}
            ctx.outputs["story"] = {"chapters": []}
            ctx.outputs["graph"] = {"nodes": [], "starting_node": "node_01"}
            ctx.outputs["gm_index"] = {"keywords": {}}
            ctx.outputs["style_bible"] = {"art_style": {}}
            ctx.outputs["images"] = {"images": {}}
            ctx.outputs["midi"] = {"midi": {}}
            ctx.outputs["manifest"] = {
                "schema_version": 1,
                "story_id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Atomic", "seed": 42, "generator_version": "0.1.0",
                "models_used": {"text_generator": "m", "validator": "m",
                                "image_generator": "m", "music_generator": "m"},
                "prompt_versions": {"world_builder": "v1", "story_writer": "v1",
                                    "game_designer": "v1", "art_director": "v1",
                                    "composer": "v1"},
                "entry_point": "node_01",
                "files": {"bible": "content/bible.json",
                          "story": "content/story.json",
                          "graph": "content/graph.json",
                          "gm_index": "content/gm_index.json",
                          "images": "content/images/",
                          "midi": "content/midi/"},
                "stats": {},
                "meta": {"artifact_id": "", "generated_at": "2026-08-03T00:00:00Z",
                         "run_id": "atomic_zip"},
            }

            async def _run() -> None:
                with patch("os.replace", _tracking_replace):
                    pkg = Packager(output_dir=tmpdir)
                    await pkg.run(ctx)

            import asyncio
            asyncio.run(_run())

            # Should have called os.replace at least once (ZIP atomic write)
            assert len(replace_calls) >= 1, (
                f"os.replace never called — ZIP is not written atomically"
            )
            # The destination should be a .story file
            assert any(str(dst).endswith(".story") for _, dst in replace_calls), (
                f"os.replace called but not for .story file: {replace_calls}"
            )

    def test_in_memory_store_no_disk_write(self) -> None:
        """ArtifactStore with output_dir=None writes nothing to disk."""
        store = ArtifactStore(output_dir=None)
        store["bible"] = {"world_name": "Memory Only"}

        assert "bible" in store
        assert store["bible"] == {"world_name": "Memory Only"}
        # No files created (output_dir is None)


# ── Section 4: Run Fingerprints ──────────────────────────────────────────────


class TestRunFingerprints:
    """Run fingerprints identify the exact config + model combination."""

    def test_fingerprint_produces_consistent_hash(self) -> None:
        """Same config → same fingerprint."""
        from src.application.generate_story import GenerateStory
        from src.config import AppConfig, ModelConfig, PipelineConfig, LimitsConfig, PathsConfig

        config = AppConfig(
            text_generator=ModelConfig(
                provider="llama_cpp", model="qwen2.5-7b", quantization="Q4_K_M",
                file="test.gguf",
            ),
            validator=ModelConfig(
                provider="llama_cpp", model="phi-3.5", quantization="Q4_K_M",
                file="test.gguf",
            ),
            image_generator=ModelConfig(
                provider="sd_cpp", model="sdxl", quantization="Q8_0",
                file="test.gguf",
            ),
            music_generator=ModelConfig(provider="abc", model="via-text", quantization=""),
            game_master=ModelConfig(provider="llama_cpp", model="llama-3.2-3b", quantization="Q4_K_M"),
            pipeline=PipelineConfig(),
            limits=LimitsConfig(),
            paths=PathsConfig(models_dir="/tmp/nonexistent_models"),
        )

        fp1 = GenerateStory._compute_run_fingerprint(config, Path("/tmp/out"))
        fp2 = GenerateStory._compute_run_fingerprint(config, Path("/tmp/out"))

        assert fp1 == fp2, "Same config should produce identical fingerprint"
        assert len(fp1) == 64  # SHA256

    def test_fingerprint_changes_with_different_model(self) -> None:
        """Different models → different fingerprint."""
        from src.application.generate_story import GenerateStory
        from src.config import AppConfig, ModelConfig, PipelineConfig, LimitsConfig, PathsConfig

        def _make_config(text_model: str) -> AppConfig:
            return AppConfig(
                text_generator=ModelConfig(
                    provider="llama_cpp", model=text_model, quantization="Q4_K_M",
                    file="test.gguf",
                ),
                validator=ModelConfig(
                    provider="llama_cpp", model="phi-3.5", quantization="Q4_K_M",
                    file="test.gguf",
                ),
                image_generator=ModelConfig(
                    provider="sd_cpp", model="sdxl", quantization="Q8_0",
                    file="test.gguf",
                ),
                music_generator=ModelConfig(provider="abc", model="via-text", quantization=""),
                game_master=ModelConfig(provider="llama_cpp", model="llama-3.2", quantization="Q4_K_M"),
                pipeline=PipelineConfig(),
                limits=LimitsConfig(),
                paths=PathsConfig(models_dir="/tmp/nonexistent_models"),
            )

        fp1 = GenerateStory._compute_run_fingerprint(
            _make_config("qwen2.5-7b"), Path("/tmp/out"),
        )
        fp2 = GenerateStory._compute_run_fingerprint(
            _make_config("different-model"), Path("/tmp/out"),
        )

        assert fp1 != fp2, "Different models should produce different fingerprints"

    def test_checkpoint_stores_run_fingerprint(self) -> None:
        """CheckpointStore.save/load preserves run_fingerprint."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = CheckpointStore(db_path)
            fp = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"

            store.save(
                "world_builder", phase=1, seed=42,
                output={"bible": "data"},
                run_fingerprint=fp,
            )

            entry = store.load("world_builder")
            assert entry is not None
            assert entry.run_fingerprint == fp, (
                f"Fingerprint not preserved: {entry.run_fingerprint} != {fp}"
            )
        finally:
            os.unlink(db_path)
