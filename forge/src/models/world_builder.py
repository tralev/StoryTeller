"""World Builder — PipelineStep that generates a structured World Bible.

Renders world_builder_v1.j2 with tone + title, calls TextGenerator,
validates against bible.schema.json, normalizes, and returns StepOutput.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from jinja2 import Template

from ..config import AppConfig
from ..interfaces import TextGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from .base import PipelineStep, StepOutput


class WorldBuilder(PipelineStep[TextGenerator]):
    """Generate a World Bible from a tone and title.

    Usage:
        builder = WorldBuilder(generator, validator, config)
        context = PipelineContext(run_id="run_01", seed=42)
        context.state["tone"] = "dark_fantasy"
        context.state["title"] = "The Ashen Marches"
        output = await builder.run(context)
        # output.data is the validated, normalized World Bible
    """

    def __init__(
        self,
        generator: TextGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
    ) -> None:
        super().__init__(
            name="world_builder",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Render the prompt, call the generator, parse JSON response.

        Args:
            context: Must have state["tone"] and state["title"].

        Returns:
            StepOutput with the World Bible dict and artifact_id.
        """
        tone = context.state.get("tone", "dark_fantasy")
        title = context.state.get("title", "Untitled World")
        temperature = context.state.get("temperature", 0.7)

        # Load and render the prompt template
        prompt_path = (
            self.config.get_prompt_path("world_builder_v1.j2")
            if self.config
            else "src/prompts/world_builder_v1.j2"
        )
        with open(prompt_path) as f:
            template_str = f.read()

        template = Template(template_str)
        prompt = template.render(tone=tone, title=title)

        # Call generator
        raw = await self.generator.generate(
            prompt=prompt,
            temperature=temperature,
            seed=context.seed,
        )

        # Add version metadata
        raw["schema_version"] = 1
        raw["generator_version"] = "0.1.0"
        raw["pipeline_version"] = 1
        raw["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        raw["model_versions"] = {
            "text_generator": f"{self.generator.model_name}-{self.generator.quantization}",
        }
        raw["seed"] = context.seed
        raw["generation_params"] = {
            "tone": tone,
            "title": title,
            "temperature": temperature,
        }

        # Generate deterministic artifact_id
        artifact_id = self._make_artifact_id(raw)

        return StepOutput(data=raw, step_name=self.name, artifact_id=artifact_id)

    @staticmethod
    def _make_artifact_id(data: dict[str, Any]) -> str:
        """Generate a short deterministic artifact ID from the content."""
        content = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"world_{digest}"
