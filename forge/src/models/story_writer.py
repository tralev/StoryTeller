"""Story Writer — PipelineStep that generates a linear story (outline + 3 chapters).

Reads the World Bible from context.outputs["bible"], generates an outline,
then writes 3 chapters sequentially. Each chapter receives the previous
chapters as context for continuity.

Uses story_writer_v1.j2 for each chapter generation.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from ..config import AppConfig
from ..interfaces import TextGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from .base import PipelineStep, StepOutput


class StoryWriter(PipelineStep[TextGenerator]):
    """Generate a 3-chapter linear story from the World Bible.

    Usage:
        writer = StoryWriter(generator, validator, config)
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["bible"] = {...}  # World Bible dict
        output = await writer.run(context)
        # output.data is the validated, normalized story with 3 chapters
    """

    CHAPTER_TITLES = ["The Beginning", "The Journey", "The Reckoning"]
    CHAPTER_WORDS = [2000, 3000, 2500]  # target word counts

    def __init__(
        self,
        generator: TextGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
    ) -> None:
        super().__init__(
            name="story_writer",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Generate story outline + 3 chapters.

        Args:
            context: Must have context.outputs["bible"].

        Returns:
            StepOutput with the complete story dict.
        """
        bible = context.outputs.get("bible")
        if bible is None:
            raise ValueError(
                "StoryWriter requires context.outputs['bible'] to be set. "
                "Run WorldBuilder first."
            )

        temperature = context.state.get("temperature", 0.7)

        # Load template once — reused for outline + all chapters
        template_str = self._load_template()

        # Step 1: Generate story outline
        outline = await self._generate_outline(
            bible, temperature, context.seed, template_str
        )

        # Step 2: Generate chapters 1-3 sequentially
        chapters = []
        previous_text = ""
        for i in range(3):
            chapter = await self._generate_chapter(
                bible=bible,
                outline=outline,
                chapter_number=i + 1,
                chapter_title=self.CHAPTER_TITLES[i],
                target_words=self.CHAPTER_WORDS[i],
                previous_chapters=previous_text,
                temperature=temperature,
                seed=context.seed + i,  # Deterministic per-chapter seed
                template_str=template_str,
            )
            chapters.append(chapter)
            previous_text += self._format_chapter_for_context(chapter)

        # Build entity_usage index
        entity_usage = self._build_entity_usage(chapters, bible)

        story = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_versions": {
                "text_generator": f"{self.generator.model_name}-{self.generator.quantization}",
            },
            "seed": context.seed,
            "based_on_bible": "bible.json",
            "chapters": chapters,
            "entity_usage": entity_usage,
        }

        artifact_id = self._make_artifact_id(story)
        return StepOutput(data=story, step_name=self.name, artifact_id=artifact_id)

    def _load_template(self) -> str:
        """Load the story writer Jinja2 template from disk."""
        prompt_path = (
            self.config.get_prompt_path("story_writer_v1.j2")
            if self.config
            else "src/prompts/story_writer_v1.j2"
        )
        with open(prompt_path) as f:
            return f.read()

    async def _generate_outline(
        self, bible: dict[str, Any], temperature: float, seed: int, template_str: str
    ) -> dict[str, Any]:
        """Generate a 3-chapter story outline from the bible."""
        from jinja2 import Template

        bible_context = self._summarize_bible(bible)
        template = Template(template_str)
        prompt = template.render(
            bible_context=bible_context,
            chapter_number=0,
            chapter_title="Outline",
            target_words=200,
            outline="Generate a 3-part story outline: one paragraph per chapter.",
            previous_chapters=None,
        )

        raw = await self.generator.generate(
            prompt=prompt, temperature=temperature, seed=seed
        )
        if not isinstance(raw, dict):
            raise ValueError(
                f"Outline generation failed: expected dict, got {type(raw).__name__}. "
                "The LLM returned malformed output."
            )
        return raw

    async def _generate_chapter(
        self,
        bible: dict[str, Any],
        outline: dict[str, Any],
        chapter_number: int,
        chapter_title: str,
        target_words: int,
        previous_chapters: str,
        temperature: float,
        seed: int,
        template_str: str,
    ) -> dict[str, Any]:
        """Generate a single chapter."""
        from jinja2 import Template

        bible_context = self._summarize_bible(bible)
        template = Template(template_str)
        prompt = template.render(
            bible_context=bible_context,
            outline=json.dumps(outline, indent=2),
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            target_words=target_words,
            previous_chapters=previous_chapters or None,
        )

        raw = await self.generator.generate(
            prompt=prompt, temperature=temperature, seed=seed
        )
        if not isinstance(raw, dict):
            raise ValueError(
                f"Chapter {chapter_number} generation failed: "
                f"expected dict, got {type(raw).__name__}. "
                "The LLM returned malformed output."
            )
        # The generator may wrap the chapter in a "chapter" key
        if "chapter" in raw:
            chapter = dict(raw["chapter"])
        else:
            chapter = dict(raw)
        # Validate the chapter has required fields
        if not isinstance(chapter, dict) or "number" not in chapter or "title" not in chapter:
            raise ValueError(
                f"Chapter {chapter_number} generation failed: "
                "output missing required fields 'number' and 'title'. "
                f"Got keys: {list(chapter.keys()) if isinstance(chapter, dict) else 'non-dict'}"
            )
        return chapter

    @staticmethod
    def _summarize_bible(bible: dict[str, Any]) -> str:
        """Build a concise summary of the bible for chapter prompts."""
        from .bible_helpers import summarize_bible
        return summarize_bible(
            bible,
            max_desc_len=100,
            show_role=True,
            show_motivation=True,
            show_flaw=True,
        )

    @staticmethod
    def _format_chapter_for_context(chapter: dict[str, Any]) -> str:
        """Format a chapter as a readable string for passing to the next chapter."""
        lines = [
            f"Chapter {chapter.get('number', '?')}: {chapter.get('title', '?')}",
            f"Summary: {chapter.get('summary', '')}",
        ]
        for scene in chapter.get("scenes", []):
            text = scene.get("text", "")
            lines.append(text[:300])  # Truncate long scenes
        return "\n\n".join(lines)

    @staticmethod
    def _build_entity_usage(
        chapters: list[dict[str, Any]], bible: dict[str, Any]
    ) -> dict[str, Any]:
        """Build a tracking index of which entities appear in which scenes."""
        usage: dict[str, dict[str, list[str]]] = {}

        for chapter in chapters:
            for scene in chapter.get("scenes", []):
                scene_id = scene.get("scene_id", "?")
                for char_id in scene.get("characters_present", []):
                    if char_id not in usage:
                        usage[char_id] = {"appears_in_scenes": [], "mentioned_in": []}
                    if scene_id not in usage[char_id]["appears_in_scenes"]:
                        usage[char_id]["appears_in_scenes"].append(scene_id)
                for ref_id in scene.get("entities_referenced", []):
                    if ref_id not in usage:
                        usage[ref_id] = {"appears_in_scenes": [], "mentioned_in": []}
                    if scene_id not in usage[ref_id]["mentioned_in"]:
                        usage[ref_id]["mentioned_in"].append(scene_id)
                loc_id = scene.get("location", "")
                if loc_id:
                    if loc_id not in usage:
                        usage[loc_id] = {"appears_in_scenes": [], "mentioned_in": []}
                    if scene_id not in usage[loc_id]["appears_in_scenes"]:
                        usage[loc_id]["appears_in_scenes"].append(scene_id)

        return usage

    @staticmethod
    def _make_artifact_id(data: dict[str, Any]) -> str:
        content = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"story_{digest}"
