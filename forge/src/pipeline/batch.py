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
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


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
    quarantined: {node_id: error_message} for items that failed but
        the failure was retryable (QUARANTINE policy).
    """

    completed: dict[str, T] = field(default_factory=dict)
    quarantined: dict[str, str] = field(default_factory=dict)
    total: int = 0
    skipped: int = 0  # Inactive nodes (no prompt/tone)

    @property
    def succeeded(self) -> int:
        return len(self.completed)

    @property
    def failed(self) -> int:
        return len(self.quarantined)


class BatchScheduler:
    """Schedule node jobs with bounded concurrency.

    Usage:
        scheduler = BatchScheduler(max_concurrency=4)
        jobs = NodeJob.from_graph(graph, key="image_prompt")
        result = await scheduler.run(jobs, step.generate_node, step)
    """

    def __init__(self, max_concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run(
        self,
        jobs: list[NodeJob],
        worker_fn: Callable[..., Awaitable[T]],
        *worker_args: Any,
        **worker_kwargs: Any,
    ) -> BatchResult[T]:
        """Execute all active node jobs with bounded concurrency.

        Args:
            jobs: List of NodeJob objects.
            worker_fn: Async callable(node_id, node, index) → T.
            *worker_args: Positional args passed to worker_fn after node_id, node, index.
            **worker_kwargs: Keyword args passed to worker_fn.

        Returns:
            BatchResult with completed and quarantined items.
        """
        result: BatchResult[T] = BatchResult(total=len(jobs))

        async def _run_one(job: NodeJob) -> None:
            if not job.active:
                result.skipped += 1
                return

            async with self._semaphore:
                try:
                    item = await worker_fn(
                        job.node_id, job.node, job.index,
                        *worker_args, **worker_kwargs,
                    )
                    result.completed[job.node_id] = item
                except Exception as e:
                    from .errors import is_retryable
                    if is_retryable(e):
                        result.quarantined[job.node_id] = str(e)
                    else:
                        raise  # Terminal — abort entire batch

        tasks = [_run_one(job) for job in jobs]
        await asyncio.gather(*tasks)
        return result
