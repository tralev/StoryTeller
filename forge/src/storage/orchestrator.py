"""Orchestrator — pipeline scheduler for the full generation pipeline.

Architecture:
  Orchestrator decides WHAT to run (phase ordering).
  JobQueue decides HOW to run (sequential vs parallel, event logging).
  PipelineStep.run() does the actual Gen→Val→Norm→Commit.

Phases:
  1. WorldBuilder           (sequential)
  2. ArtDirector            (sequential)
  3. StoryWriter            (sequential)
  4. GameDesigner           (sequential)
  5. Image + Music          (parallel — different models)
  6. GmIndexer              (sequential)
  7. Packager               (sequential)

Supports checkpointing for resume after interruption.
"""

from __future__ import annotations

import time
from typing import Any

from ..job_queue import JobQueue, PipelineContext
from ..models.base import PipelineError, StepOutput
from ..storage.checkpoint import CheckpointStore


class Orchestrator:
    """Schedule and run the full generation pipeline through a JobQueue.

    Usage:
        queue = JobQueue(event_log_path="pipeline_events.jsonl")
        orchestrator = Orchestrator(checkpoint_store, steps, queue)
        context = PipelineContext(run_id="run_01", seed=42)
        context.state["tone"] = "dark_fantasy"
        context.state["title"] = "The Ashen Marches"
        output = await orchestrator.run(context)
    """

    def __init__(
        self,
        checkpoint_store: CheckpointStore,
        steps: dict[str, Any],
        queue: JobQueue | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store
        self.steps = steps
        self.queue = queue or JobQueue()
        self.run_fingerprint: str = ""

    async def run(self, context: PipelineContext) -> StepOutput:
        context.state["start_time"] = time.time()

        # Determine starting phase (resume support)
        highest = self.checkpoint_store.get_highest_completed_phase()
        start_phase = 1 if highest == 0 else highest + 1

        # Phase definitions: (phase_number, step_names, parallel)
        phases: list[tuple[int, list[str], bool]] = [
            (1, ["world_builder"], False),
            (2, ["art_director"], False),
            (3, ["story_writer"], False),
            (4, ["game_designer"], False),
            (5, ["image_generator", "music_generator"], True),
            (6, ["indexer"], False),
            (7, ["packager"], False),
        ]

        last_output: StepOutput | None = None

        for phase_num, step_names, parallel in phases:
            if phase_num < start_phase:
                # Already completed — restore from checkpoint
                for name in step_names:
                    entry = self.checkpoint_store.load(name)
                    if entry:
                        import json as _json

                        # Restore using canonical output_key, not internal step name
                        # This ensures downstream steps find "bible", not "world_builder"
                        key = entry.output_key or name
                        context.outputs[key] = _json.loads(entry.output_json)
                continue

            if parallel and len(step_names) > 1:
                # Parallel phase — multiple steps via JobQueue.execute_parallel
                steps_and_ids = [
                    (name, self.steps[name]) for name in step_names
                ]
                results = await self.queue.execute_parallel(steps_and_ids, context)

                for name, result in zip(step_names, results):
                    if isinstance(result, Exception):
                        raise PipelineError(name, 1, [str(result)])
                    if isinstance(result, StepOutput):
                        context.outputs[name] = result.data
                        self._save_checkpoint(name, phase_num, context.seed, result)
                        last_output = result
            else:
                # Sequential phase — one step at a time
                for name in step_names:
                    step = self.steps.get(name)
                    if step is None:
                        raise ValueError(f"Unknown step: {name}")

                    output: StepOutput = await self.queue.execute_step(
                        step, context, name,
                    )
                    context.outputs[name] = output.data
                    self._save_checkpoint(name, phase_num, context.seed, output)
                    last_output = output

        if last_output is None:
            return StepOutput(
                data={"error": "No phases completed"},
                step_name="orchestrator",
            )
        return last_output

    def _save_checkpoint(
        self,
        name: str,
        phase: int,
        seed: int,
        output: StepOutput,
    ) -> None:
        self.checkpoint_store.save(
            step_name=name,
            output_key=CheckpointStore.canonical_key(name),
            phase=phase,
            seed=seed,
            output=output.data,
            artifact_id=output.artifact_id or "",
            run_fingerprint=self.run_fingerprint,
        )
