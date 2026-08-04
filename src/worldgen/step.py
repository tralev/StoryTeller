"""ProceduralWorldStep — generates a world snapshot with no LLM.

This is a pure-Python PipelineStep. It generates a complete
WorldSnapshot from a seed using deterministic algorithms, then
stores it in context.outputs for downstream WorldBuilder enrichment.
"""

from __future__ import annotations

from typing import Any

from ..job_queue import PipelineContext
from ..models.base import PipelineStep, StepOutput
from .generator import generate_world


class ProceduralWorldStep(PipelineStep[Any]):
    """Generate a procedural WorldSnapshot from seed only.

    No LLM required — pure deterministic algorithms.
    Output key: "world_snapshot".

    Usage:
        step = ProceduralWorldStep()
        output = await step.run(context)
        # context.outputs["world_snapshot"] = {...}
    """

    output_key = "world_snapshot"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            name="procedural_world",
            generator=None,
            validator=None,
            **kwargs,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Generate the world snapshot from seed and state parameters.

        Reads optional generation params from context.state:
          - world_size: (width, height) tuple, default (64, 64)
          - max_civs: max civilizations, default 4
          - history_years: simulation years, default 200
        """
        seed = context.seed
        world_size = context.state.get("world_size", (64, 64))
        max_civs = context.state.get("max_civs", 4)
        history_years = context.state.get("history_years", 200)

        snapshot = generate_world(
            seed=seed,
            width=world_size[0],
            height=world_size[1],
            max_civs=max_civs,
            history_years=history_years,
        )

        return StepOutput(
            data=snapshot.to_dict(),
            step_name=self.name,
            artifact_id=f"world_snap_{seed:08x}",
        )
