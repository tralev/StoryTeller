"""Single owner of plan traversal, model scopes, cancellation and failures."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .context import RunContext
from .events import PipelineFailed, PipelineStarted
from .plan import PipelinePlan, StepSpec

SegmentExecutor = Callable[[list[StepSpec]], Awaitable[None]]


@dataclass
class PipelineRunner:
    """Execute a validated plan in contiguous model-resource segments.

    Step mechanics remain injectable while the v1 steps are migrated. The
    runner nevertheless owns validation, traversal, resource transitions,
    cancellation and terminal failure emission.
    """

    plan: PipelinePlan
    model_manager: Any

    async def run(self, context: RunContext, execute_segment: SegmentExecutor) -> None:
        self.plan.validate()
        context.cancellation.raise_if_cancelled()
        context.events.emit(
            PipelineStarted(
                run_id=context.run_id,
                seed=context.seed,
                title=context.title,
                tone=context.tone,
            )
        )
        try:
            for role, segment in self.plan.group_by_model_role():
                context.cancellation.raise_if_cancelled()
                if role is None:
                    await execute_segment(segment)
                else:
                    async with self.model_manager.resource_scope(role):
                        await execute_segment(segment)
                context.cancellation.raise_if_cancelled()
        except BaseException as error:
            context.events.emit(
                PipelineFailed(
                    run_id=context.run_id,
                    errors=[str(error)],
                )
            )
            raise
