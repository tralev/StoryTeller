"""Orchestrator — pipeline scheduler for the full generation pipeline.

Phases (sequential unless noted):
  1. WorldBuilder
  2. ArtDirector
  3. StoryWriter
  4. GameDesigner
  5. ImageGeneratorStep + MusicGeneratorStep (parallel)
  6. GmIndexer
  7. Packager

Supports checkpointing for resume after interruption.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..job_queue import PipelineContext
from ..models.base import PipelineError, StepOutput
from ..storage.checkpoint import CheckpointStore


class Orchestrator:
    """Schedule and run the full generation pipeline.

    Usage:
        orchestrator = Orchestrator(checkpoint_store, steps)
        context = PipelineContext(run_id="run_01", seed=42)
        context.state["tone"] = "dark_fantasy"
        context.state["title"] = "The Ashen Marches"
        output = await orchestrator.run(context)
    """

    def __init__(
        self,
        checkpoint_store: CheckpointStore,
        steps: dict[str, Any],
    ) -> None:
        self.checkpoint_store = checkpoint_store
        self.steps = steps
        self.events: list[dict[str, Any]] = []

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
                        import json as jmod

                        context.outputs[name] = jmod.loads(entry.output_json)
                continue

            self._log_event(phase_num, "start", step_names)

            if parallel and len(step_names) > 1:
                # Run steps concurrently
                tasks = [
                    self._run_step(name, context, phase_num)
                    for name in step_names
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for name, result in zip(step_names, results):
                    if isinstance(result, Exception):
                        self._log_event(phase_num, "error", [name], str(result))
                        raise PipelineError(name, 1, [str(result)])
                    if isinstance(result, StepOutput):
                        last_output = result
            else:
                for name in step_names:
                    last_output = await self._run_step(name, context, phase_num)

            self._log_event(phase_num, "end", step_names)

        if last_output is None:
            return StepOutput(
                data={"error": "No phases completed"},
                step_name="orchestrator",
            )
        return last_output

    async def _run_step(
        self, name: str, context: PipelineContext, phase: int
    ) -> StepOutput:
        step = self.steps.get(name)
        if step is None:
            raise ValueError(f"Unknown step: {name}")

        output: StepOutput = await step.run(context)
        context.outputs[name] = output.data

        # Save checkpoint
        self.checkpoint_store.save(
            step_name=name,
            phase=phase,
            seed=context.seed,
            output=output.data,
            artifact_id=output.artifact_id or "",
        )

        return output

    def _log_event(
        self,
        phase: int,
        event: str,
        steps: list[str],
        detail: str = "",
    ) -> None:
        self.events.append({
            "phase": phase,
            "event": event,
            "steps": steps,
            "ts": time.time(),
            "detail": detail,
        })
