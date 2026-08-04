"""World Builder — PipelineStep that generates a structured World Bible.

Renders world_builder_v1.j2 (or v2 with world_snapshot) with tone + title,
calls TextGenerator, validates against bible.schema.json, normalizes, and
returns StepOutput.

Phase 7.5: When context.outputs contains "world_snapshot", the builder
uses v2.j2 with procedural world constraints injected.
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

    output_key = "bible"

    def __init__(
        self,
        generator: TextGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name="world_builder",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
            **kwargs,
        )

    async def generate(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        """Render the prompt, call the generator, parse JSON response.

        Args:
            context: Must have state["tone"] and state["title"].

        Returns:
            StepOutput with the World Bible dict and artifact_id.
        """
        tone = context.tone  # Phase 5.6N N4: typed run spec
        title = context.title
        temperature = context.temperature

        # Phase 7.5: Check for procedural world snapshot
        snapshot = context.outputs.get_world_snapshot()
        use_v2 = snapshot is not None and isinstance(snapshot, dict)

        template_name = "world_builder_v2.j2" if use_v2 else "world_builder_v1.j2"
        prompt_path = (
            self.config.get_prompt_path(template_name)
            if self.config
            else f"src/prompts/{template_name}"
        )
        with open(prompt_path) as f:
            template_str = f.read()

        template = Template(template_str)
        # Phase 7.5: Inject procedural world constraints into v2 prompt
        snapshot_context = ""
        if use_v2 and snapshot:
            from ..worldgen.adapter import snapshot_dict_to_bible_context
            snapshot_context = snapshot_dict_to_bible_context(snapshot)

        prompt = template.render(
            tone=tone, title=title,
            world_snapshot_context=snapshot_context,
        )

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
