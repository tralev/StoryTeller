"""Tests for Phase 5.6 P — Per-Node Asset Checkpoints.

Covers:
  P4: quarantine records are structured with stable error codes and are
      persisted into the aggregated batch output
  P5: resume reuses only missing/invalid/fingerprint-mismatch-free assets —
      a checkpoint from a different run seed is regenerated
  P6: per-node retry limits driven by ExecutionPolicy
  P7: identical asset outputs with worker counts 1 and N (determinism)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.batch import BatchResult, BatchScheduler, NodeJob, QuarantineRecord
from src.pipeline.errors import ConfigurationError, GenerationError
from src.pipeline.policy import ExecutionPolicy
from src.storage.checkpoint import CheckpointStore


def _make_jobs(node_count: int) -> list[NodeJob]:
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
    """Deterministic disk-writing worker (mirrors generate_node)."""
    path = Path(out_dir) / f"{node_id}.png"
    data = f"data-{node_id}-{index}-{base_seed}".encode()
    path.write_bytes(data)
    return {
        "image_path": str(path),
        "image_bytes": len(data),
        "seed": base_seed + index,
    }


@pytest.fixture
def store() -> CheckpointStore:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = CheckpointStore(path)
    yield s
    os.unlink(path)


# ── P4: structured quarantine records ───────────────────────────────────────


class TestQuarantineRecords:
    """Quarantined nodes carry stable error codes + attempt counts."""

    @pytest.mark.asyncio
    async def test_quarantine_record_has_stable_code(self, tmp_path: Path) -> None:
        """A permanently-failing retryable worker produces a GEN_001 record."""
        async def _always_fail(node_id: str, node: dict[str, Any], index: int,
                               out_dir: Path) -> dict[str, Any]:
            raise GenerationError("image_generator", "transient model glitch")

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=3),
        )
        result = await scheduler.run(_make_jobs(1), _always_fail, tmp_path)

        assert result.succeeded == 0
        assert len(result.quarantined) == 1
        rec = result.quarantined["node_00"]
        assert isinstance(rec, QuarantineRecord)
        assert rec.code == "GEN_001", f"Expected stable code GEN_001, got {rec.code}"
        assert rec.retryable is True
        assert rec.attempts == 4, (
            f"Expected 4 attempts (3 retries + first), got {rec.attempts}"
        )
        assert "transient" in rec.message
        assert rec.details.get("step") == "image_generator"

    @pytest.mark.asyncio
    async def test_unknown_error_aborts_batch(self, tmp_path: Path) -> None:
        """Non-StoryTeller errors are terminal and abort the batch.

        Unknown exceptions have no stable code (is_retryable → False), so
        they are never quarantined — they propagate and abort.
        """
        async def _boom(node_id: str, node: dict[str, Any], index: int,
                        out_dir: Path) -> dict[str, Any]:
            raise RuntimeError("programming error")

        scheduler = BatchScheduler(max_concurrency=1)
        with pytest.raises(RuntimeError, match="programming error"):
            await scheduler.run(_make_jobs(1), _boom, tmp_path)

    def test_record_to_dict_shape(self) -> None:
        rec = QuarantineRecord(
            node_id="node_01", code="GEN_001", message="boom",
            attempts=4, retryable=True, details={"step": "image_generator"},
        )
        d = rec.to_dict()
        assert d["node_id"] == "node_01"
        assert d["quarantined"] is True
        assert d["error_code"] == "GEN_001"
        assert d["message"] == "boom"
        assert d["attempts"] == 4
        assert d["retryable"] is True
        assert d["details"] == {"step": "image_generator"}

# ── P5: run-seed fingerprint on resume ──────────────────────────────────────


class TestRunSeedResume:
    """Assets from a different seed are never reused on resume."""

    @pytest.mark.asyncio
    async def test_same_seed_resumes(self, store: CheckpointStore, tmp_path: Path) -> None:
        img = tmp_path / "node_00.png"
        img.write_bytes(b"asset from seed 42")
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img), "seed": 42},
            seed=42, run_seed=42,
        )

        calls = 0

        async def _counting(node_id: str, node: dict[str, Any], index: int,
                            out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=1, checkpoint_store=store, step_name="image_generator",
            expected_seed=42,
        )
        result = await scheduler.run(_make_jobs(1), _counting, tmp_path)

        assert result.resumed == 1
        assert calls == 0, "Same-seed asset must be reused"

    @pytest.mark.asyncio
    async def test_different_seed_regenerates(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """P5: checkpoint from seed 42 is rejected when resuming with seed 99."""
        img = tmp_path / "node_00.png"
        img.write_bytes(b"asset from seed 42")
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img), "seed": 42},
            seed=42, run_seed=42,
        )

        scheduler = BatchScheduler(
            max_concurrency=1, checkpoint_store=store, step_name="image_generator",
            expected_seed=99,
        )
        result = await scheduler.run(_make_jobs(1), _disk_worker, tmp_path)

        assert result.resumed == 0, "Fingerprint-mismatched asset must regenerate"
        assert result.succeeded == 1
        # Old checkpoint deleted, new one carries run_seed=99
        rec = store.load_all_node_records("image_generator")["node_00"]
        assert rec.run_seed == 99

    @pytest.mark.asyncio
    async def test_legacy_checkpoint_without_seed_trusted(
        self, store: CheckpointStore, tmp_path: Path,
    ) -> None:
        """Backward compat: no stored run_seed → no fingerprint check."""
        img = tmp_path / "node_00.png"
        img.write_bytes(b"legacy asset")
        store.save_node(
            "image_generator", "node_00",
            {"image_path": str(img), "seed": 42},
            seed=42,
        )

        calls = 0

        async def _counting(node_id: str, node: dict[str, Any], index: int,
                            out_dir: Path) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=1, checkpoint_store=store, step_name="image_generator",
            expected_seed=42,
        )
        result = await scheduler.run(_make_jobs(1), _counting, tmp_path)

        assert result.resumed == 1
        assert calls == 0


# ── P6: per-node retry limits ───────────────────────────────────────────────


class TestPerNodeRetries:
    """Retryable failures retry per ExecutionPolicy before quarantine."""

    @pytest.mark.asyncio
    async def test_succeeds_after_transient_failures(self, tmp_path: Path) -> None:
        """Fails twice (retryable) then succeeds → completed, not quarantined."""
        state = {"calls": 0}

        async def _flaky(node_id: str, node: dict[str, Any], index: int,
                         out_dir: Path) -> dict[str, Any]:
            state["calls"] += 1
            if state["calls"] < 3:  # First two attempts fail
                raise GenerationError("image_generator", "transient")
            return await _disk_worker(node_id, node, index, out_dir)

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=3),
        )
        result = await scheduler.run(_make_jobs(1), _flaky, tmp_path)

        assert result.succeeded == 1
        assert result.quarantined == {}
        assert state["calls"] == 3, f"Expected 3 attempts, got {state['calls']}"

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_quarantines(self, tmp_path: Path) -> None:
        """Always-retryable failure → quarantined after max_retries+1 attempts."""
        state = {"calls": 0}

        async def _always(node_id: str, node: dict[str, Any], index: int,
                          out_dir: Path) -> dict[str, Any]:
            state["calls"] += 1
            raise GenerationError("image_generator", "keeps failing")

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=2),
        )
        result = await scheduler.run(_make_jobs(1), _always, tmp_path)

        assert len(result.quarantined) == 1
        assert result.quarantined["node_00"].attempts == 3, (
            "2 retries + 1 first attempt = 3 total attempts"
        )
        assert state["calls"] == 3

    @pytest.mark.asyncio
    async def test_zero_retries_means_single_attempt(self, tmp_path: Path) -> None:
        """max_retries=0 → exactly one attempt, then quarantine."""
        state = {"calls": 0}

        async def _always(node_id: str, node: dict[str, Any], index: int,
                          out_dir: Path) -> dict[str, Any]:
            state["calls"] += 1
            raise GenerationError("image_generator", "nope")

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=0),
        )
        result = await scheduler.run(_make_jobs(1), _always, tmp_path)

        assert len(result.quarantined) == 1
        assert result.quarantined["node_00"].attempts == 1
        assert state["calls"] == 1

    @pytest.mark.asyncio
    async def test_terminal_error_aborts_immediately(self, tmp_path: Path) -> None:
        """Non-retryable errors abort the batch without retrying."""
        state = {"calls": 0}

        async def _terminal(node_id: str, node: dict[str, Any], index: int,
                            out_dir: Path) -> dict[str, Any]:
            state["calls"] += 1
            raise ConfigurationError("models.yaml", "Missing model file")

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=3),
        )
        with pytest.raises(ConfigurationError, match="Missing model file"):
            await scheduler.run(_make_jobs(1), _terminal, tmp_path)

        assert state["calls"] == 1, "Terminal errors must not be retried"


# ── P7: determinism across worker counts ────────────────────────────────────


class TestWorkerCountDeterminism:
    """Identical asset outputs with worker counts 1 and N."""

    @pytest.mark.asyncio
    async def test_concurrency_1_vs_4_identical(self, tmp_path: Path) -> None:
        """Same deterministic worker produces identical outputs regardless of
        concurrency — no shared state, no ordering dependence."""
        out_a = tmp_path / "out_a"
        out_b = tmp_path / "out_b"
        out_a.mkdir()
        out_b.mkdir()

        async def run_with(concurrency: int, out_dir: Path) -> dict[str, Any]:
            scheduler = BatchScheduler(max_concurrency=concurrency)
            result = await scheduler.run(_make_jobs(5), _disk_worker, out_dir, base_seed=42)
            # Compare the deterministic fields only (paths differ by dir)
            return {
                nid: {"seed": m["seed"], "image_bytes": m["image_bytes"]}
                for nid, m in result.completed.items()
            }

        serial = await run_with(1, out_a)
        parallel = await run_with(4, out_b)

        assert serial == parallel, (
            f"Outputs differ across worker counts:\n serial={serial}\n parallel={parallel}"
        )

        # File bytes must be identical too
        for i in range(5):
            nid = f"node_{i:02d}"
            assert (out_a / f"{nid}.png").read_bytes() == (out_b / f"{nid}.png").read_bytes()

    @pytest.mark.asyncio
    async def test_same_concurrency_repeated_identical(self, tmp_path: Path) -> None:
        """Same concurrency, repeated runs → identical outputs."""
        out1 = tmp_path / "o1"
        out2 = tmp_path / "o2"
        out1.mkdir()
        out2.mkdir()

        async def run_with(out_dir: Path) -> dict[str, Any]:
            scheduler = BatchScheduler(max_concurrency=3)
            result = await scheduler.run(_make_jobs(5), _disk_worker, out_dir, base_seed=7)
            return {
                nid: {"seed": m["seed"], "image_bytes": m["image_bytes"]}
                for nid, m in result.completed.items()
            }

        assert await run_with(out1) == await run_with(out2)
