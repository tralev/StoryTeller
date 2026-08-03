"""MusicGeneratorStep — PipelineStep for parallel MIDI generation.

Reads graph nodes, generates ABC notation via TextGenerator (composer_v1.j2),
validates ABC, converts to MIDI via music21.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from jinja2 import Template

from ..config import AppConfig
from ..interfaces import MusicGenerator, TextGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from .base import PipelineStep, StepOutput


class MusicGeneratorStep(PipelineStep[TextGenerator]):
    """Generate MIDI music for graph nodes from scene text and music_tone.

    Uses composer_v1.j2 via TextGenerator for ABC notation,
    then MusicGenerator for ABC→MIDI conversion.

    Usage:
        step = MusicGeneratorStep(text_generator, music_generator, validator, config)
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["graph"] = {...}
        output = await step.run(context)
        # output.data maps node_id → midi metadata
    """

    def __init__(
        self,
        text_generator: TextGenerator,
        music_generator: MusicGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.QUARANTINE,
    ) -> None:
        super().__init__(
            name="music_generator",
            generator=text_generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
        )
        self.music_generator = music_generator

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Generate MIDI for all graph nodes with music_tone set.

        Requires context.outputs["graph"].
        """
        graph = context.outputs.get("graph")
        if graph is None:
            raise ValueError(
                "MusicGeneratorStep requires context.outputs['graph']. "
                "Run GameDesigner first."
            )

        nodes = graph.get("nodes", [])
        template_str = self._load_template()

        midi_files: dict[str, dict[str, Any]] = {}
        nodes_with_tone = 0

        for i, node in enumerate(nodes):
            node_id = node.get("node_id", f"node_{i:02d}")
            music_tone = node.get("music_tone", "").strip()
            if not music_tone:
                continue
            nodes_with_tone += 1

            scene_text = node.get("text", "")
            mood = node.get("mood", music_tone)

            try:
                # Render composer prompt
                template = Template(template_str)
                prompt = template.render(
                    scene_text=scene_text,
                    mood=mood,
                    music_tone=music_tone,
                )

                seed = context.seed + i
                abc_raw = await self.generator.generate(
                    prompt=prompt,
                    temperature=0.3,
                    seed=seed,
                )
                # ABC might come back as string or dict
                abc_text = abc_raw if isinstance(abc_raw, str) else json.dumps(abc_raw)

                # Validate ABC
                valid = self.music_generator.validate_abc(abc_text)
                if not valid:
                    continue  # Skip invalid ABC (QUARANTINE mode)

                # Convert to MIDI
                midi_bytes = self.music_generator.abc_to_midi(abc_text)
            except Exception:
                continue  # QUARANTINE: skip failed nodes

            midi_files[node_id] = {
                "abc_notation": abc_text,
                "midi_bytes_length": len(midi_bytes),
                "music_tone": music_tone,
                "seed": seed,
            }

        if nodes_with_tone > 0 and len(midi_files) == 0:
            raise RuntimeError(
                f"MIDI generation failed for all {nodes_with_tone} nodes. "
                "Check that the model is loaded and ABC generation is working."
            )

        result = {
            "midi": midi_files,
            "midi_count": len(midi_files),
        }

        artifact_id = self._make_artifact_id(result)
        return StepOutput(data=result, step_name=self.name, artifact_id=artifact_id)

    # ── helpers ─────────────────────────────────────────────────────────

    def _load_template(self) -> str:
        path = (
            self.config.get_prompt_path("composer_v1.j2")
            if self.config
            else "src/prompts/composer_v1.j2"
        )
        with open(path) as f:
            return f.read()

    @staticmethod
    def _make_artifact_id(data: dict[str, Any]) -> str:
        content = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"mid_{digest}"
