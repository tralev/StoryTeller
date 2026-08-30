from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from src.domain.run_spec import RunSpec
from src.pipeline.context import CancellationToken, RunContext
from src.pipeline.events import InMemoryEventSink
from src.pipeline.plan import PipelinePlan, StepSpec
from src.pipeline.runner import PipelineRunner


class Manager:
    def __init__(self) -> None:
        self.roles: list[str] = []

    @asynccontextmanager
    async def resource_scope(self, role: str):
        self.roles.append(role)
        yield


@pytest.mark.asyncio
async def test_runner_owns_plan_and_resource_traversal() -> None:
    plan = PipelinePlan(
        [
            StepSpec("a", "bible", model_role="text"),
            StepSpec("b", "story", requires=("bible",), model_role="text"),
            StepSpec("c", "packager", requires=("story",)),
        ]
    )
    manager = Manager()
    sink = InMemoryEventSink()
    context = RunContext("run", RunSpec(seed=1), events=sink)
    segments: list[list[str]] = []

    async def execute(segment: list[StepSpec]) -> None:
        segments.append([step.id for step in segment])

    await PipelineRunner(plan, manager).run(context, execute)
    assert manager.roles == ["text"]
    assert segments == [["a", "b"], ["c"]]
    assert sink.events[0].event_type == "pipeline_started"


@pytest.mark.asyncio
async def test_runner_propagates_cancellation_before_work() -> None:
    token = CancellationToken()
    token.cancel()
    context = RunContext("run", RunSpec(seed=1), cancellation=token)
    called = False

    async def execute(_segment: list[StepSpec]) -> None:
        nonlocal called
        called = True

    with pytest.raises(BaseException) as caught:
        await PipelineRunner(PipelinePlan.production_v2(), Manager()).run(context, execute)
    assert isinstance(caught.value, __import__("asyncio").CancelledError)
    assert not called
