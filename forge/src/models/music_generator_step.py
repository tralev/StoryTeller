"""MusicGeneratorStep — PipelineStep for parallel MIDI generation.

Reads graph nodes, generates ABC notation via TextGenerator (composer_v1.j2),
validates ABC, converts to MIDI via music21.

Writes MIDI files to output_dir/midi/.
Stores file paths (not raw bytes) in context.outputs for the Packager.

Supports node-level checkpointing for resume after interruption.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jinja2 import Template

from ..config import AppConfig
from ..interfaces import MusicGenerator, TextGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from .base import PipelineStep, StepOutput


class MusicGeneratorStep(PipelineStep[TextGenerator]):
    """Generate MIDI music for graph nodes from scene text and music_tone.

    output_key = "midi"

    Writes .mid files to output_dir/midi/.

    Usage:
        step = MusicGeneratorStep(text_gen, music_gen, output_dir="output")
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["graph"] = {...}
        output = await step.run(context)
        # output.data maps node_id → {midi_path, abc_notation, ...}
    """

    def __init__(
        self,
        text_generator: TextGenerator,
        music_generator: MusicGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.QUARANTINE,
        output_dir: str = "output",
    ) -> None:
        self.music_generator = music_generator
        self.output_dir = Path(output_dir)
        super().__init__(
            name="music_generator",
            generator=text_generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Generate MIDI for all graph nodes with music_tone set."""
        graph = context.outputs.get("graph")
        if graph is None:
            raise ValueError(
                "MusicGeneratorStep requires context.outputs['graph']. "
                "Run GameDesigner first."
            )

        nodes = graph.get("nodes", [])
        template_str = self._load_template()

        # Ensure output directory exists
        midi_dir = self.output_dir / "midi"
        midi_dir.mkdir(parents=True, exist_ok=True)

        midi_files: dict[str, dict[str, Any]] = {}
        nodes_with_tone = 0
        completed_nodes: set[str] = set()

        # Check for previously completed nodes (resume support)
        prev_output = context.outputs.get("midi")
        if isinstance(prev_output, dict):
            prev_midi = prev_output.get("midi", {})
            for nid, meta in prev_midi.items():
                midi_path = Path(meta.get("midi_path", ""))
                if midi_path.exists():
                    midi_files[nid] = meta
                    completed_nodes.add(nid)

        for i, node in enumerate(nodes):
            node_id = node.get("node_id", f"node_{i:02d}")
            if node_id in completed_nodes:
                continue  # Already done (resume)

            music_tone = node.get("music_tone", "").strip()
            if not music_tone:
                continue
            nodes_with_tone += 1

            scene_text = node.get("text", "")
            mood = node.get("mood", music_tone)

            try:
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
                abc_text = abc_raw if isinstance(abc_raw, str) else json.dumps(abc_raw)

                valid = self.music_generator.validate_abc(abc_text)
                if not valid:
                    continue

                midi_bytes = self.music_generator.abc_to_midi(abc_text)
            except Exception:
                continue  # QUARANTINE

            # Write to disk
            midi_path = midi_dir / f"{node_id}.mid"
            midi_path.write_bytes(midi_bytes)

            midi_files[node_id] = {
                "abc_notation": abc_text,
                "midi_path": str(midi_path),
                "midi_bytes": len(midi_bytes),
                "music_tone": music_tone,
                "seed": seed,
            }

        if nodes_with_tone > 0 and len(midi_files) == len(completed_nodes):
            raise RuntimeError(
                f"MIDI generation failed for all {nodes_with_tone} new nodes. "
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
