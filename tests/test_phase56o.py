"""Tests for Phase 5.6 O — Atomic Persistence and Recovery.

Covers:
  O2: image/MIDI media outputs are written atomically (tmp + rename)
  O3: node checkpoints store the artifact content hash + canonical path
  O4: resume reconciles the stored hash against the actual disk artifact —
      missing or corrupted files invalidate the checkpoint and regenerate
  O6: crash-window tests — artifact-before-checkpoint and
      checkpoint-before-artifact failures
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.storage.checkpoint import CheckpointStore, NodeCheckpointRecord
from src.storage.fs import atomic_write_bytes


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_jobs(node_count: int) -> list:
    """NodeJob list with image_prompt triggers for every node."""
    from src.pipeline.batch import NodeJob
    return [
        NodeJob(
            node_id=f"node_{i:02d}",
            node={"node_id": f"node_{i:02d}", "image_prompt": "prompt"},
            index=i,
            active=True,
        )
        for i in range(node_count)
    ]


async def _disk_worker(
    node_id: str,
    node: dict[str, Any],
    index: int,
    out_dir: Path,
    base_seed: int = 0,
) -> dict[str, Any]:
    """Worker that writes a real file (mirrors generate_node)."""
    path = Path(out_dir) / f"{node_id}.png"
    data = f"data-{node_id}-{index}".encode()
    path.write_bytes(data)
    return {
        "image_path": str(path),
        "image_bytes": len(data),
        "seed": base_seed + index,
    }


# ── O2: atomic media writes ──────────────────────────────────────────────────


class TestAtomicWriteBytes:
    """src/storage/fs.atomic_write_bytes crash-safe semantics."""

    def test_writes_target_no_tmp_leftover(self, tmp_path: Path) -> None:
        target = tmp_path / "img" / "node_01.png"
        data = b"\x89PNG\x0d\x0a" + b"\x00" * 32

        atomic_write_bytes(target, data)

        assert target.read_bytes() == data
        # No temp file survives
        assert list(tmp_path.rglob("*.tmp")) == []
        assert list(tmp_path.rglob("*.png.tmp")) == []

    def test_replaces_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "node_01.png"
        target.write_bytes(b"old content")

        atomic_write_bytes(target, b"new content")

        assert target.read_bytes() == b"new content"
        assert list(tmp_path.glob("*.tmp")) == []

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "node.mid"
        atomic_write_bytes(target, b"MIDI")
        assert target.read_bytes() == b"MIDI"

    def test_failure_cleans_tmp_and_preserves_original(self, tmp_path: Path) -> None:
        target = tmp_path / "node.png"
        target.write_bytes(b"original")

        # Force a failure mid-write: monkeypatch the temp write to raise
        import src.storage.fs as fs_mod

        original_write = Path.write_bytes

        def _boom(self: Path, data: bytes) -> None:
            if self.name == "node.png.tmp":
                raise OSError("disk full")
            return original_write(self, data)

        fs_mod.Path.write_bytes = _boom  # type: ignore[assignment]
        try:
            with pytest.raises(OSError, match="disk full"):
                atomic_write_bytes(target, b"new")
        finally:
            fs_mod.Path.write_bytes = original_write  # type: ignore[method-assign]

        # Original untouched, no temp file left
        assert target.read_bytes() == b"original"
        assert not (tmp_path / "node.png.tmp").exists()


# ── O3: checkpoint metadata ──────────────────────────────────────────────────


class TestNodeCheckpointMetadata:
    """Node checkpoints persist content hash + canonical path."""

    @pytest.fixture
    def store(self) -> CheckpointStore:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        store = CheckpointStore(path)
        yield store
        os.unlink(path)

    def test_save_stores_hash_and_path(self, store: CheckpointStore) -> None:
        store.save_node(
            "image_generator", "node_01",
            {"image_path": "/art/node_01.png", "seed": 42},
            seed=42,
            content_hash="abc123",
            artifact_path="/art/node_01.png",
        )
        records = store.load_all_node_records("image_generator")
        rec = records["node_01"]
        assert isinstance(rec, NodeCheckpointRecord)
        assert rec.content_hash == "abc123"
        assert rec.artifact_path == "/art/node_01.png"
        assert rec.output["image_path"] == "/art/node_01.png"

    def test_legacy_save_defaults_empty(self, store: CheckpointStore) -> None:
        store.save_node(
            "image_generator", "node_01",
            {"image_path": "/art/node_01.png", "seed": 42},
            seed=42,
        )
        rec = store.load_all_node_records("image_generator")["node_01"]
        assert rec.content_hash == ""
        assert rec.artifact_path == ""

    def test_load_all_nodes_backward_compatible(self, store: CheckpointStore) -> None:
        store.save_node(
            "image_generator", "node_01",
            {"image_path": "/art/node_01.png", "seed": 42},
            seed=42,
            content_hash="abc123",
            artifact_path="/art/node_01.png",
        )
        # Legacy accessor still returns plain output dicts
        plain = store.load_all_nodes("image_generator")
        assert plain["node_01"]["image_path"] == "/art/node_01.png"
        assert "content_hash" not in plain["node_01"]

    def test_load_all_node_records_empty(self, store: CheckpointStore) -> None:
        assert store.load_all_node_records("image_generator") == {}


# ── O4 + O6: resume reconciliation and crash windows ─────────────────────────


class TestBatchSchedulerReconciliation:
    """Resume reconciles stored hash vs actual artifact on disk."""

    @pytest.fixture
    def store(self) -> CheckpointStore:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        store = CheckpointStore(path)
        yield store
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_hash_match_resumes_without_work(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """Intact file + matching hash → node restored, worker not called."""
        from src.pipeline.batch import BatchScheduler

        img_path = tmp_path / "node_00.png"
        data = b"complete image bytes"
        img_path.write_bytes(data)

        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img_path), "seed": 42},
            seed=42,
            content_hash=_sha256(data),
            artifact_path=str(img_path),
        )

        calls = 0

        async def _counting_worker(node_id: str, node: dict[str, Any],
                                   index: int, out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _counting_worker, tmp_path)

        assert result.resumed == 1
        assert result.succeeded == 1
        assert calls == 0, "Worker must not run for a verified node"

    @pytest.mark.asyncio
    async def test_checkpoint_before_artifact_regenerates(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """O6 crash window: checkpoint saved but artifact file missing."""
        from src.pipeline.batch import BatchScheduler

        # Simulate: checkpoint committed, then the media file was lost
        lost_path = tmp_path / "node_00.png"
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(lost_path), "seed": 42},
            seed=42,
            content_hash=_sha256(b"lost bytes"),
            artifact_path=str(lost_path),
        )
        assert not lost_path.exists()

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _disk_worker, tmp_path)

        # Not trusted → regenerated, checkpoint re-saved with new hash
        assert result.resumed == 0
        assert result.succeeded == 1
        assert lost_path.exists()
        rec = store.load_all_node_records("image_generator")["node_00"]
        assert rec.content_hash == _sha256(lost_path.read_bytes())
        assert rec.artifact_path == str(lost_path)

    @pytest.mark.asyncio
    async def test_hash_mismatch_regenerates(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """O4: file exists but content differs from stored hash (corruption)."""
        from src.pipeline.batch import BatchScheduler

        img_path = tmp_path / "node_00.png"
        img_path.write_bytes(b"tampered content")

        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img_path), "seed": 42},
            seed=42,
            content_hash=_sha256(b"original content"),
            artifact_path=str(img_path),
        )

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _disk_worker, tmp_path)

        assert result.resumed == 0, "Corrupt file must not be trusted"
        assert result.succeeded == 1
        # File now contains fresh worker output and the checkpoint matches it
        rec = store.load_all_node_records("image_generator")["node_00"]
        assert rec.content_hash == _sha256(img_path.read_bytes())

    @pytest.mark.asyncio
    async def test_thumbnail_deletion_regenerates(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """O4: the hash covers image AND thumbnail — a deleted thumbnail
        invalidates the checkpoint even when the image is intact."""
        from src.pipeline.batch import BatchScheduler

        img = tmp_path / "node_00.png"
        thumb = tmp_path / "thumbnails" / "node_00.png"
        thumb.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"image bytes")
        thumb.write_bytes(b"thumb bytes")

        # Combined hash over both files (as the scheduler computes it)
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img), "thumb_path": str(thumb), "seed": 42},
            seed=42,
            content_hash=_sha256(b"image bytes" + b"thumb bytes"),
            artifact_path=str(img),
        )

        # Crash window: only the thumbnail is lost
        thumb.unlink()

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _disk_worker, tmp_path)

        assert result.resumed == 0, "Missing thumbnail must invalidate checkpoint"
        assert result.succeeded == 1

    @pytest.mark.asyncio
    async def test_thumbnail_hash_match_resumes(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """O4: intact image + thumbnail with matching combined hash → resume."""
        from src.pipeline.batch import BatchScheduler

        img = tmp_path / "node_00.png"
        thumb = tmp_path / "thumbnails" / "node_00.png"
        thumb.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"image bytes")
        thumb.write_bytes(b"thumb bytes")

        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img), "thumb_path": str(thumb), "seed": 42},
            seed=42,
            content_hash=_sha256(b"image bytes" + b"thumb bytes"),
            artifact_path=str(img),
        )

        calls = 0

        async def _counting_worker(node_id: str, node: dict[str, Any],
                                   index: int, out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _counting_worker, tmp_path)

        assert result.resumed == 1
        assert calls == 0

    @pytest.mark.asyncio
    async def test_artifact_before_checkpoint_regenerates(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """O6 crash window: artifact file exists but no checkpoint was saved."""
        from src.pipeline.batch import BatchScheduler

        # Orphan file on disk — a previous crash after write but before
        # the checkpoint commit. No checkpoint exists for node_00.
        orphan = tmp_path / "node_00.png"
        orphan.write_bytes(b"orphan from crashed run")

        calls = 0

        async def _counting_worker(node_id: str, node: dict[str, Any],
                                   index: int, out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _counting_worker, tmp_path)

        # No checkpoint → full regeneration (orphan file is overwritten)
        assert result.resumed == 0
        assert calls == 1
        assert result.succeeded == 1
        rec = store.load_all_node_records("image_generator")["node_00"]
        assert rec.content_hash == _sha256(orphan.read_bytes())
        assert rec.artifact_path == str(orphan)

    @pytest.mark.asyncio
    async def test_legacy_no_hash_trusts_existence(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """Backward compat: legacy checkpoint (no hash) resumes on existence."""
        from src.pipeline.batch import BatchScheduler

        img_path = tmp_path / "node_00.png"
        img_path.write_bytes(b"old data")
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img_path), "seed": 42},
            seed=42,
        )

        calls = 0

        async def _counting_worker(node_id: str, node: dict[str, Any],
                                   index: int, out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(1), _counting_worker, tmp_path)

        assert result.resumed == 1
        assert calls == 0

    @pytest.mark.asyncio
    async def test_scheduler_saves_hash_for_new_nodes(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """O3 integration: after a fresh run, every node checkpoint carries the
        content hash and canonical path of the written file."""
        from src.pipeline.batch import BatchScheduler

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(3), _disk_worker, tmp_path)

        assert result.succeeded == 3
        records = store.load_all_node_records("image_generator")
        assert len(records) == 3
        for node_id, rec in records.items():
            path = Path(rec.artifact_path)
            assert path.exists()
            assert rec.content_hash == _sha256(path.read_bytes())

    @pytest.mark.asyncio
    async def test_mixed_resume_and_regeneration(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """Verified nodes resume; corrupted/missing ones regenerate."""
        from src.pipeline.batch import BatchScheduler

        # node_00: intact + matching hash → resume
        good = tmp_path / "node_00.png"
        good_data = b"good node"
        good.write_bytes(good_data)
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(good), "seed": 42},
            seed=42, content_hash=_sha256(good_data), artifact_path=str(good),
        )
        # node_01: checkpoint exists but file missing → regenerate
        missing = tmp_path / "node_01.png"
        store.save_node(
            "image_generator", "node_01",
            {"image_path": str(missing), "seed": 43},
            seed=43, content_hash=_sha256(b"x"), artifact_path=str(missing),
        )

        calls = 0

        async def _counting_worker(node_id: str, node: dict[str, Any],
                                   index: int, out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=2, checkpoint_store=store, step_name="image_generator",
        )
        result = await scheduler.run(_make_jobs(2), _counting_worker, tmp_path)

        assert result.resumed == 1
        assert calls == 1
        assert result.succeeded == 2
        assert result.completed["node_00"]["image_path"] == str(good)
