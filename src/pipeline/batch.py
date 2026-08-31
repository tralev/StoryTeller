"""BatchScheduler — maps batch steps into individually schedulable node jobs.

Phase 5.5H: Image and music steps currently loop over all nodes internally,
hiding progress and preventing per-node checkpointing. The BatchScheduler
separates planning from execution:

  1. PlanImageJobs(graph) → list[NodeJob]
  2. scheduler.run(jobs, worker_fn, max_concurrency=N)
  3. Aggregate results

Each node job runs independently with a configurable worker limit
(asyncio.Semaphore). The scheduler reports structured results:
completed, quarantined, and failed counts.

Phase 5.5H item 3: Per-node checkpointing — accepts an optional
CheckpointStore. On resume, already-completed nodes are skipped.
After each node completes, its output is saved as a node checkpoint.
If all nodes crash, resume picks up where it left off without
restarting finished nodes.

Phase 5.6 O3/O4: Each node checkpoint stores the SHA-256 content hash and
canonical path of the artifact file. On resume, the stored hash is reconciled
against the actual file on disk — a missing or corrupted file invalidates the
checkpoint and the node is regenerated (atomic writes make partial files
impossible to publish).

Phase 5.6 P4/P5/P6: Quarantine records carry stable error codes (not bare
strings) and are persisted into the aggregated output. Resume only reuses
assets that are present, hash-valid, AND produced by the same run seed —
anything missing, invalid, or fingerprint-mismatched is regenerated. Retryable
node failures retry up to the ExecutionPolicy limit before being quarantined.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class QuarantineRecord:
    """Structured record of a quarantined (failed but retryable) node.

    Replaces the bare error-message string previously stored in
    ``BatchResult.quarantined`` with stable, machine-readable data:
    a stable error code (Phase 5.6 P4), the message, and attempt count.
    """

    node_id: str
    code: str  # Stable error code, e.g. "GEN_001" (src.pipeline.errors)
    message: str
    attempts: int  # Number of attempts before giving up
    retryable: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persistence into the aggregated batch output."""
        return {
            "node_id": self.node_id,
            "quarantined": True,
            "error_code": self.code,
            "message": self.message,
            "attempts": self.attempts,
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass
class NodeJob:
    """A single unit of batch work — one node image or one MIDI track.

    Carries enough context for the worker function to generate the
    asset without accessing the full graph.
    """

    node_id: str
    node: dict[str, Any]  # The graph node dict
    index: int  # Position in the graph (for seed derivation)
    active: bool = True  # False if node should be skipped (no prompt/tone)

    @classmethod
    def from_graph(
        cls,
        graph: dict[str, Any],
        *,
        key: str = "image_prompt",  # The node field that triggers generation
    ) -> list[NodeJob]:
        """Build a list of NodeJob from graph nodes.

        Only nodes with a non-empty value for `key` get active=True.
        """
        jobs: list[NodeJob] = []
        for i, node in enumerate(graph.get("nodes", [])):
            nid = node.get("node_id", f"node_{i:02d}")
            has_trigger = bool(node.get(key, "").strip())
            jobs.append(cls(node_id=nid, node=node, index=i, active=has_trigger))
        return jobs


@dataclass
class BatchResult(Generic[T]):
    """Structured result of batch execution.

    completed: {node_id: result} for successfully generated items.
    quarantined: {node_id: QuarantineRecord} for items that exhausted
        their retries on a retryable failure (Phase 5.6 P4/P6).
    resumed: Number of nodes skipped because they already had checkpoints.
    """

    completed: dict[str, T] = field(default_factory=dict)
    quarantined: dict[str, QuarantineRecord] = field(default_factory=dict)
    total: int = 0
    skipped: int = 0  # Inactive nodes (no prompt/tone)
    resumed: int = 0  # Nodes restored from checkpoint (Phase 5.5H)

    @property
    def succeeded(self) -> int:
        return len(self.completed)

    @property
    def failed(self) -> int:
        return len(self.quarantined)


class BatchScheduler:
    """Schedule node jobs with bounded concurrency and optional per-node checkpointing.

    Usage:
        scheduler = BatchScheduler(max_concurrency=4, checkpoint_store=store)
        jobs = NodeJob.from_graph(graph, key="image_prompt")
        result = await scheduler.run(jobs, step.generate_node, style_bible, seed, img_dir)

    With checkpointing:
        - Before running each job, checks if a node checkpoint exists.
        - If found AND the file on disk still exists, skips the node (resume).
        - After each node completes, saves a checkpoint so a crash mid-batch
          doesn't lose finished nodes.
    """

    def __init__(
        self,
        max_concurrency: int = 4,
        checkpoint_store: Any = None,
        step_name: str = "",
        policy: Any = None,  # ExecutionPolicy
        expected_seed: int | None = None,  # Phase 5.6 P5: run identity
    ) -> None:
        from .policy import ExecutionPolicy

        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._checkpoint_store = checkpoint_store
        self._step_name = step_name
        self._policy = policy or ExecutionPolicy.default()
        self._max_attempts = self._policy.total_attempts()
        self._expected_seed = expected_seed

    async def run(
        self,
        jobs: list[NodeJob],
        worker_fn: Callable[..., Awaitable[T]],
        *worker_args: Any,
        **worker_kwargs: Any,
    ) -> BatchResult[T]:
        """Execute all active node jobs with bounded concurrency.

        Phase 5.5H: Checkpoint resume + per-node checkpointing.
        Phase 5.6K: Cancellation-safe — on CancelledError, stops
            scheduling new nodes, waits briefly for active ones, and
            returns partial results. Atomic writes prevent partial files.
        """
        result: BatchResult[T] = BatchResult(total=len(jobs))
        cancelled: bool = False

        # Phase 5.5H + 5.6 O4/P5: Restore already-completed nodes from
        # checkpoints. A checkpoint is trusted only if:
        #   1. ALL of the node's media files exist (image, thumbnail, midi), AND
        #   2. their combined content hash matches what was recorded at save
        #      time (missing/corrupted files regenerate), AND
        #   3. the checkpoint was produced by the SAME run seed (fingerprint
        #      mismatch regenerates — assets from another seed are never reused).
        # Anything else — missing, invalid, or fingerprint-mismatched — is
        # scheduled again.
        if self._checkpoint_store is not None and self._step_name:
            restored = self._checkpoint_store.load_all_node_records(self._step_name)
            for node_id, record in restored.items():
                media = _media_paths(record.output)
                ok = False
                if media and all(p.exists() for p in media):
                    if record.content_hash:
                        ok = _media_sha256(record.output) == record.content_hash
                    else:
                        # Legacy checkpoint without a stored hash —
                        # trust existence (previous behavior).
                        ok = True
                if ok and (
                    self._expected_seed is not None
                    and record.run_seed is not None
                    and record.run_seed != self._expected_seed
                ):
                    # Phase 5.6 P5: produced by a different seed → regenerate
                    ok = False
                if not ok:
                    self._checkpoint_store.delete_node(self._step_name, node_id)
                    continue
                result.completed[node_id] = record.output
                result.resumed += 1

        async def _run_one(job: NodeJob) -> None:
            nonlocal cancelled
            if cancelled:
                return
            if not job.active:
                result.skipped += 1
                return
            if job.node_id in result.completed:
                return

            # Phase 5.6 P6: retryable failures retry up to the ExecutionPolicy
            # limit; only then is the node quarantined with a structured record.
            # Terminal errors abort the whole batch immediately.
            attempts = 0
            while True:
                attempts += 1
                try:
                    async with self._semaphore:
                        if cancelled:
                            return
                        item = await worker_fn(
                            job.node_id,
                            job.node,
                            job.index,
                            *worker_args,
                            **worker_kwargs,
                        )
                    # Success
                    result.completed[job.node_id] = item

                    # Phase 5.5H + 5.6 O3/P5: Save per-node checkpoint with the
                    # artifact's content hash + canonical path + run seed so a
                    # later resume can verify the file is intact and matches
                    # this run's identity.
                    if self._checkpoint_store is not None and self._step_name:
                        item_seed = (
                            item.get("seed", job.index) if isinstance(item, dict) else job.index
                        )
                        content_hash, artifact_path = _artifact_metadata(item)
                        self._checkpoint_store.save_node(
                            step_name=self._step_name,
                            node_id=job.node_id,
                            output=item if isinstance(item, dict) else {"value": item},
                            seed=item_seed,
                            attempt_count=attempts,
                            content_hash=content_hash,
                            artifact_path=artifact_path,
                            run_seed=self._expected_seed,
                        )
                    return

                except asyncio.CancelledError:
                    cancelled = True
                    # Don't re-raise — let other active tasks finish cleanly
                    return
                except Exception as e:
                    from .errors import error_code, is_retryable

                    retryable = is_retryable(e)
                    if retryable and attempts < self._max_attempts:
                        # Retry per ExecutionPolicy. Immediate retry (no backoff)
                        # is acceptable: the semaphore is released between
                        # attempts, so other nodes keep progressing.
                        continue
                    if not retryable:
                        raise  # Terminal error — abort entire batch
                    # Exhausted retries → structured quarantine record (P4)
                    result.quarantined[job.node_id] = QuarantineRecord(
                        node_id=job.node_id,
                        code=error_code(e),
                        message=str(e),
                        attempts=attempts,
                        retryable=True,
                        details=getattr(e, "details", None) or {},
                    )
                    return

        tasks = [asyncio.create_task(_run_one(job)) for job in jobs]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # Phase 5.6K: Cancel raised to the gather — mark all pending as skipped
            cancelled = True
            # Wait briefly for active tasks to finish
            pending = [t for t in tasks if not t.done()]
            if pending:
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        return result


# Canonical order for per-node media files (image, thumbnail, score, midi).
# Order matters — the combined hash must be deterministic across save/resume.
_MEDIA_KEYS = ("image_path", "thumb_path", "score_path", "midi_path")


def _media_paths(output: dict[str, Any]) -> list[Path]:
    """All media files referenced by a node output that currently exist."""
    paths: list[Path] = []
    for key in _MEDIA_KEYS:
        raw = output.get(key)
        if raw:
            path = Path(str(raw))
            if path.exists():
                paths.append(path)
    return paths


def _media_sha256(output: dict[str, Any]) -> str:
    """Combined SHA-256 over ALL media files of a node (O4).

    Files are hashed in canonical key order (image, thumbnail, midi) so the
    digest is identical at save and resume time. Covering every media file
    means a corrupted or deleted thumbnail invalidates the hash even when
    the image itself is intact.
    """
    hasher = hashlib.sha256()
    for key in _MEDIA_KEYS:
        raw = output.get(key)
        if not raw:
            continue
        path = Path(str(raw))
        if not path.exists():
            continue
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _artifact_metadata(item: Any) -> tuple[str, str]:
    """Extract (content_hash, artifact_path) from a worker result.

    Media workers return dicts with ``image_path`` / ``thumb_path`` /
    ``midi_path`` keys. The hash covers ALL media files on disk — exactly
    what O4 verifies at resume time. If no media file exists (e.g.
    pure-memory test fakes), the hash is empty and only the primary path
    is recorded.
    """
    if not isinstance(item, dict):
        return "", ""
    primary = item.get("image_path") or item.get("midi_path") or ""
    if not _media_paths(item):
        return "", str(primary) if primary else ""
    return _media_sha256(item), str(primary)
