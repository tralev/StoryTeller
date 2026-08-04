"""Async job queue — dispatches pipeline steps with event logging.

Architecture (resolved split-brain):
  Orchestrator (WHAT to run)
      │
      ▼
  JobQueue.execute_step() ──► PipelineStep.run()  (sequential)
  JobQueue.execute_parallel() ──► asyncio.gather(PipelineStep.run()...)  (parallel)
      │
      ▼
  Each PipelineStep.run() handles:
    Generate → Validate → Normalize → Commit (with retries)

The JobQueue provides: event logging, timing, failure tracking.
PipelineStep provides: the actual Gen→Val→Norm→Commit loop.

No duplication — PipelineStep.run() is the single source of truth for
step execution. JobQueue is a thin scheduling/dispatch layer.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import AppConfig
from .artifact_store import ArtifactStore


class JobType(Enum):
    """Types of pipeline jobs — used for event log categorization."""

    GENERATE_BIBLE = "generate_bible"
    GENERATE_STYLE_BIBLE = "generate_style_bible"
    GENERATE_OUTLINE = "generate_outline"
    GENERATE_CHAPTER = "generate_chapter"
    CONSISTENCY_CHECK = "consistency_check"
    EXTRACT_DECISION_POINTS = "extract_decision_points"
    BUILD_GRAPH_SKELETON = "build_graph_skeleton"
    GENERATE_NODE = "generate_node"
    GENERATE_IMAGE = "generate_image"
    GENERATE_MUSIC = "generate_music"
    BUILD_GM_INDEX = "build_gm_index"
    PACKAGE = "package"


class FailurePolicy(Enum):
    """What to do when a step fails after max retries."""

    ABORT = "abort"  # Stop entire pipeline (default for sequential phases)
    QUARANTINE = "quarantine"  # Skip failed item, continue with others


class JobStatus(Enum):
    """Current state of a job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PipelineContext:
    """Context passed through every pipeline step. Accumulates outputs and state.

    Attributes:
        run_id: Unique identifier for this pipeline run.
        seed: Reproducibility seed passed to all generators.
        config: Application configuration.
        output_dir: If set, every write to context.outputs also flushes
            a JSON file to this directory — preventing OOM during long
            pipeline runs. When None (default, tests), operates purely
            in-memory.
        artifacts: Disk-backed ArtifactStore. Access via context.outputs
            (property alias) for backward compatibility.
        feedback: Accumulated validation errors for retry feedback.
        state: Arbitrary key/value pairs for pipeline-wide state.
    """

    run_id: str
    seed: int
    config: AppConfig | None = None
    output_dir: str | None = None
    artifacts: ArtifactStore = field(default_factory=ArtifactStore)
    feedback: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Replace default ArtifactStore with disk-backed one if output_dir set."""
        if self.output_dir is not None:
            from .artifact_store import ArtifactStore as _Store

            self.artifacts = _Store(output_dir=self.output_dir)

    @property
    def outputs(self) -> ArtifactStore:
        """Backward-compatible alias for artifacts.

        Pipeline steps use context.outputs["bible"] = data and
        context.outputs.get("bible") — both work transparently with
        the disk-backed ArtifactStore.

        Every write also flushes a JSON file to output_dir if configured.
        """
        return self.artifacts

    def add_feedback(self, errors: list[str]) -> None:
        """Accumulate validation errors for retry feedback."""
        self.feedback.extend(errors)

    def clear_feedback(self) -> None:
        """Clear feedback after a successful generation."""
        self.feedback.clear()


@dataclass
class JobResult:
    """Result of a completed (or failed) step execution."""

    job_id: str
    status: JobStatus
    output: Any = None
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class JobQueue:
    """Dispatches pipeline steps with event logging and timing.

    Delegates all execution to PipelineStep.run() — the single source
    of truth for Gen→Val→Norm→Commit. JobQueue provides:
      - Sequential dispatch: execute_step()
      - Parallel dispatch: execute_parallel() using asyncio.gather
      - Event logging: JSONL output for long-running pipeline monitoring
      - Timing: per-step duration tracking
      - Result tracking: job_id → JobResult dictionary

    Usage:
        queue = JobQueue(worker_count=4, event_log_path="events.jsonl")

        # Sequential phases — one step at a time
        await queue.execute_step(world_builder, context, "wb")
        await queue.execute_step(story_writer, context, "sw")

        # Parallel phase — image + music run concurrently
        results = await queue.execute_parallel(
            [("img", image_step), ("mus", music_step)],
            context,
        )
    """

    def __init__(
        self,
        worker_count: int = 4,
        event_log_path: str | None = None,
        event_sink: Any = None,  # Phase 5.6J: EventSink
        run_id: str = "",  # Phase 5.6J: for typed events
    ) -> None:
        self.worker_count = worker_count
        self.event_log_path = event_log_path
        self.results: dict[str, JobResult] = {}
        self.run_id = run_id
        # Phase 5.6J: Use EventSink if provided, else fall back to legacy file logging
        if event_sink is not None:
            self._sink = event_sink
        elif event_log_path:
            from .pipeline.events import JsonlEventSink
            self._sink = JsonlEventSink(event_log_path)
        else:
            from .pipeline.events import NullEventSink
            self._sink = NullEventSink()

    async def execute_step(
        self,
        step: Any,  # PipelineStep[T] — avoids circular import
        context: PipelineContext,
        job_id: str,
        job_type: JobType | None = None,
    ) -> Any:
        """Execute a single pipeline step sequentially.

        Delegates to step.run(context) — all Gen→Val→Norm→Commit logic
        lives in PipelineStep.run(). This method adds event logging and timing.

        Phase 5.6J: Emits typed StepStarted/StepCompleted/StepFailed events
        with the real run_id.
        """
        # Phase 5.6J: Typed event emission
        from .pipeline.events import StepCompleted, StepFailed, StepStarted
        self._sink.emit(StepStarted(
            run_id=self.run_id, step_id=job_id,
        ))

        t0 = time.time()

        try:
            output = await step.run(context)
            elapsed = time.time() - t0
            # Store output in context so downstream steps can access it.
            _STEP_KEY_MAP: dict[str, str] = {
                "procedural_world": "world_snapshot",  # Phase 7.5
                "world_builder": "bible",
                "art_director": "style_bible",
                "story_writer": "story",
                "game_designer": "graph",
                "image_generator": "images",
                "music_generator": "midi",
                "indexer": "gm_index",
            }
            if hasattr(output, 'data'):
                key = _STEP_KEY_MAP.get(job_id, job_id)
                context.outputs[key] = output.data
            self.results[job_id] = JobResult(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                output=output,
                duration_seconds=elapsed,
            )
            self._sink.emit(StepCompleted(
                run_id=self.run_id, step_id=job_id,
                artifact_key=_STEP_KEY_MAP.get(job_id, job_id),
                duration_s=round(elapsed, 1),
            ))
            return output

        except Exception as e:
            elapsed = time.time() - t0
            self.results[job_id] = JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                errors=[str(e)],
                duration_seconds=elapsed,
            )
            from .pipeline.errors import StoryTellerError, is_retryable
            retryable = is_retryable(e) if isinstance(e, StoryTellerError) else False
            self._sink.emit(StepFailed(
                run_id=self.run_id, step_id=job_id,
                error_message=str(e), retryable=retryable,
            ))
            raise

    async def execute_parallel(
        self,
        steps: list[tuple[str, Any]],  # [(job_id, PipelineStep)]
        context: PipelineContext,
    ) -> list[Any]:
        """Execute multiple pipeline steps concurrently via asyncio.gather.

        Image and music generation run in parallel because they use
        different models (SDXL vs music21). Text generation steps are
        sequential (shared LLM) and use execute_step() individually.

        Uses return_exceptions=True so one failing step doesn't cancel
        others — matching QUARANTINE semantics.

        Args:
            steps: List of (job_id, PipelineStep) tuples.
            context: Pipeline context shared across all parallel steps.

        Returns:
            List of StepOutput or Exception for each step.
        """
        tasks = [
            self.execute_step(step, context, job_id)
            for job_id, step in steps
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def get_result(self, job_id: str) -> JobResult | None:
        """Retrieve the result of a previously executed step."""
        return self.results.get(job_id)

    @property
    def completed_count(self) -> int:
        return sum(
            1 for r in self.results.values()
            if r.status == JobStatus.COMPLETED
        )

    @property
    def failed_count(self) -> int:
        return sum(
            1 for r in self.results.values()
            if r.status == JobStatus.FAILED
        )

    # ── event sink access ───────────────────────────────────────────────

    @property
    def event_sink(self) -> Any:
        """Phase 5.6J: Access the EventSink for external event emission."""
        return self._sink
