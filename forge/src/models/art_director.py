"""Art Director — PipelineStep that generates a Style Bible.

Reads the World Bible from context.outputs["bible"], renders
style_bible_v1.j2 with entity summaries, calls TextGenerator,
validates against style_bible.schema.json, and returns StepOutput.
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


class ArtDirector(PipelineStep[TextGenerator]):
    """Generate a Style Bible from the World Bible.

    output_key = "style_bible"

    Usage:
        director = ArtDirector(generator, validator, config)
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["bible"] = {...}  # World Bible dict
        output = await director.run(context)
        # output.data is the validated, normalized Style Bible
    """

    def __init__(
        self,
        generator: TextGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name="art_director",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
            **kwargs,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Render the prompt with bible summary, call generator.

        Args:
            context: Must have context.outputs["bible"] with the World Bible.

        Returns:
            StepOutput with the Style Bible dict and artifact_id.

        Raises:
            ValueError: If bible is not in context.outputs.
        """
        bible = context.outputs.get("bible")
        if bible is None:
            raise ValueError(
                "ArtDirector requires context.outputs['bible'] to be set. "
                "Run WorldBuilder first."
            )

        tone = bible.get("narrative_rules", {}).get("tone", "dark_fantasy")
        temperature = context.state.get("temperature", 0.7)

        # Collect characters and locations for the template
        entities = bible.get("entities", {})
        characters = entities.get("characters", [])
        locations = entities.get("locations", [])

        # Build a concise bible summary for the prompt
        bible_summary = self._summarize_bible(bible)

        # Load and render template
        prompt_path = (
            self.config.get_prompt_path("style_bible_v1.j2")
            if self.config
            else "src/prompts/style_bible_v1.j2"
        )
        with open(prompt_path) as f:
            template_str = f.read()

        template = Template(template_str)
        prompt = template.render(
            bible_summary=bible_summary,
            tone=tone,
            characters=characters,
            locations=locations,
        )

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
        raw["seed"] = context.seed

        artifact_id = self._make_artifact_id(raw)
        return StepOutput(data=raw, step_name=self.name, artifact_id=artifact_id)

    @staticmethod
    def _summarize_bible(bible: dict[str, Any]) -> str:
        """Build a concise text summary of the World Bible for the prompt."""
        from .bible_helpers import summarize_bible
        return summarize_bible(
            bible,
            categories=[
                "characters",
                "locations",
                "factions",
                "creatures",
                "artifacts",
                "events",
            ],
            max_desc_len=80,
        )

    @staticmethod
    def _make_artifact_id(data: dict[str, Any]) -> str:
        content = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"style_{digest}"
