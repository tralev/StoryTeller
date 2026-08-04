"""Game Designer — PipelineStep that converts linear story into CYOA branching graph.

Uses game_designer_v1.j2 in 3 modes:
  Mode 1 — decision_points: extract decision points from story
  Mode 2 — graph_skeleton: build node structure + connections
  Mode 3 — node_text: generate text + choices for each node

Merge: skeleton (structural) + text (content) → graph.schema.json compliant nodes.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, cast

from jinja2 import Template

from ..config import AppConfig
from ..interfaces import TextGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from .base import PipelineStep, StepOutput


class GameDesigner(PipelineStep[TextGenerator]):
    """Convert a linear story into a branching CYOA graph.

    output_key = "graph"

    Usage:
        designer = GameDesigner(generator, validator, config)
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["bible"] = {...}
        context.outputs["story"] = {...}
        output = await designer.run(context)
        # output.data is the validated, normalized CYOA graph
    """

    TARGET_NODES = 15

    def __init__(
        self,
        generator: TextGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name="game_designer",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
            **kwargs,
        )

    async def generate(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        """Run all 3 modes and produce a complete graph.

        Requires context.outputs["bible"] and context.outputs["story"].
        """
        bible = context.outputs.get_bible()  # Phase 5.6N N5
        story = context.outputs.get_story()
        if bible is None:
            raise ValueError(
                "GameDesigner requires context.outputs['bible']. Run WorldBuilder first."
            )
        if story is None:
            raise ValueError(
                "GameDesigner requires context.outputs['story']. Run StoryWriter first."
            )

        temperature = context.temperature  # Phase 5.6N N4
        template_str = self._load_template()
        store = context.checkpoint_store  # Phase 5.6L

        # Compute dependency hash from story — if story changes, all sub-checkpoints invalidate
        dep_hash = self._hash_dict(cast(dict[str, Any], story))

        # Mode 1: Extract decision points (with sub-checkpoint)
        story_text = self._format_story_for_prompt(cast(dict[str, Any], story))
        dp_result = await self._load_or_generate(
            store=store, step="game_designer", sub_id="decision_points",
            dep_hash=dep_hash,
            fn=self._extract_decision_points,
            story_text=story_text, temperature=temperature,
            seed=context.seed, template_str=template_str,
        )
        decision_points = dp_result.get("decision_points", [])
        if not decision_points:
            raise ValueError(
                "GameDesigner: Mode 1 returned empty decision_points. "
                "The story did not contain enough branch points. "
                "Check that the story has a clear middle chapter with choices."
            )

        # Mode 2: Build graph skeleton (with sub-checkpoint)
        # Skeleton depends on both story and decision_points
        skeleton_dep = dep_hash + self._hash_dict(dp_result)
        bible_summary = self._summarize_bible_for_skeleton(cast(dict[str, Any], bible))
        skeleton = await self._load_or_generate(
            store=store, step="game_designer", sub_id="skeleton",
            dep_hash=skeleton_dep,
            fn=self._build_graph_skeleton,
            bible_summary=bible_summary, decision_points=decision_points,
            temperature=temperature, seed=context.seed, template_str=template_str,
        )
        skeleton_nodes = skeleton.get("nodes", [])

        # Collect flags from skeleton for the flags_catalog
        flags_catalog: dict[str, str] = {}
        for sn in skeleton_nodes:
            for ch in sn.get("choices", []):
                for flag in ch.get("sets_flags", []):
                    if flag not in flags_catalog:
                        flags_catalog[flag] = f"Flag set by: {ch.get('choice_text', '?')}"

        # Mode 3: Generate text for each node + merge (with per-node sub-checkpoints)
        # Each node depends on story + skeleton
        node_dep = dep_hash + self._hash_dict(skeleton)
        nodes = []
        endings = []
        story_summary = story.get("chapters", [{}])[0].get("summary", story_text[:200])
        for i, sn in enumerate(skeleton_nodes):
            node_id = sn.get("node_id", f"node_{i:02d}")
            # Build neighbor info
            neighbors = self._build_neighbors(skeleton_nodes, sn)
            text_result = await self._load_or_generate(
                store=store, step="game_designer", sub_id=node_id,
                dep_hash=node_dep,
                fn=self._generate_node_text,
                bible=bible, story_summary=story_summary,
                node=sn, neighbors=neighbors, active_flags=[],
                temperature=temperature, seed=context.seed + i,
                template_str=template_str,
            )
            merged = self.merge_node(sn, text_result)
            nodes.append(merged)

            # Track endings
            if sn.get("endings", {}).get("is_ending"):
                endings.append({
                    "node_id": node_id,
                    "type": sn.get("endings", {}).get("ending_type", "dark"),
                    "title": sn.get("endings", {}).get("ending_title", "Ending"),
                })

        # Build full graph
        graph: dict[str, Any] = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_versions": {
                "text_generator": f"{self.generator.model_name}-{self.generator.quantization}",
            },
            "seed": context.seed,
            "starting_node": "node_01",
            "flags_catalog": flags_catalog,
            "nodes": nodes,
            "endings_summary": endings[:3],  # At most 3
        }

        artifact_id = self._make_artifact_id(graph)
        return StepOutput(data=graph, step_name=self.name, artifact_id=artifact_id)

    # ── prompt helpers ──────────────────────────────────────────────────

    def _load_template(self) -> str:
        path = (
            self.config.get_prompt_path("game_designer_v1.j2")
            if self.config
            else "src/prompts/game_designer_v1.j2"
        )
        with open(path) as f:
            return f.read()

    @staticmethod
    def _format_story_for_prompt(story: dict[str, Any]) -> str:
        """Serialize story chapters into a single text blob for Mode 1."""
        parts: list[str] = []
        for ch in story.get("chapters", []):
            parts.append(f"Chapter {ch.get('number', '?')}: {ch.get('title', '?')}")
            parts.append(ch.get("summary", ""))
            for sc in ch.get("scenes", []):
                parts.append(sc.get("text", "")[:500])
        return "\n\n".join(parts)

    @staticmethod
    def _summarize_bible_for_skeleton(bible: dict[str, Any]) -> str:
        """Brief bible summary for the graph skeleton prompt."""
        from .bible_helpers import summarize_bible
        return summarize_bible(
            bible,
            include_world=False,
            include_magic=False,
            max_desc_len=60,
        )

    @staticmethod
    def _build_neighbors(
        nodes: list[dict[str, Any]], current: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Build neighbor list for Mode 3 node_text prompt."""
        targets = {ch.get("target_node", "") for ch in current.get("choices", [])}
        return [{"node_id": n.get("node_id", "?"), "description": n.get("description", "")}
                for n in nodes if n.get("node_id", "") in targets]

    # ── Mode 1: decision points ─────────────────────────────────────────

    async def _extract_decision_points(
        self, story_text: str, temperature: float, seed: int, template_str: str
    ) -> dict[str, Any]:
        template = Template(template_str)
        prompt = template.render(mode="decision_points", story_text=story_text)
        raw = await self.generator.generate(prompt=prompt, temperature=temperature, seed=seed)
        if not isinstance(raw, dict):
            raise ValueError(f"Mode 1: expected dict, got {type(raw).__name__}")
        return raw

    # ── Mode 2: graph skeleton ──────────────────────────────────────────

    async def _build_graph_skeleton(
        self,
        bible_summary: str,
        decision_points: list[dict[str, Any]],
        temperature: float,
        seed: int,
        template_str: str,
    ) -> dict[str, Any]:
        template = Template(template_str)
        prompt = template.render(
            mode="graph_skeleton",
            decision_points=json.dumps(decision_points, indent=2),
            bible_summary=bible_summary,
            target_nodes=self.TARGET_NODES,
        )
        raw = await self.generator.generate(prompt=prompt, temperature=temperature, seed=seed)
        if not isinstance(raw, dict):
            raise ValueError(f"Mode 2: expected dict, got {type(raw).__name__}")
        return raw

    # ── Mode 3: node text ───────────────────────────────────────────────

    async def _generate_node_text(
        self,
        bible: dict[str, Any],
        story_summary: str,
        node: dict[str, Any],
        neighbors: list[dict[str, Any]],
        active_flags: list[str],
        temperature: float,
        seed: int,
        template_str: str,
    ) -> dict[str, Any]:
        node_id = node["node_id"]
        choices = node.get("choices", [])
        template = Template(template_str)
        bible_context = self._summarize_bible_for_node(bible, node)
        prompt = template.render(
            mode="node_text",
            bible_context=bible_context,
            story_summary=story_summary,
            node_id=node_id,
            node_description=node.get("description", ""),
            previous_node_text="",
            neighbors=neighbors,
            active_flags=json.dumps(active_flags),
            choice_count=len(choices),
            choices=choices,
            conditional_text=False,
        )
        raw = await self.generator.generate(prompt=prompt, temperature=temperature, seed=seed)
        if not isinstance(raw, dict):
            raise ValueError(f"Mode 3: expected dict, got {type(raw).__name__}")
        return raw

    @staticmethod
    def _summarize_bible_for_node(bible: dict[str, Any], node: dict[str, Any]) -> str:
        """Summarize only the entities present in this node."""
        from .bible_helpers import summarize_bible
        present_chars = set(node.get("present_characters", []))
        present_loc = node.get("present_location", "")
        return summarize_bible(
            bible,
            include_world=False,
            include_magic=False,
            categories=["characters", "locations"],
            max_desc_len=80,
            show_role=True,
            filter_ids={
                "characters": present_chars,
                "locations": {present_loc},
            },
        )

    # ── merge ───────────────────────────────────────────────────────────

    @staticmethod
    def merge_node(
        skeleton_node: dict[str, Any],
        text_node: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge skeleton (structural) + text (content) into a complete node."""
        merged: dict[str, Any] = {
            "node_id": skeleton_node.get("node_id", "?"),
            "chapter": skeleton_node.get("chapter", 0),
            "scene_type": skeleton_node.get("scene_type", "exploration"),
            "text": text_node.get("text", ""),
            "present_characters": skeleton_node.get("present_characters", []),
            "present_location": skeleton_node.get("present_location", ""),
            "present_creatures": skeleton_node.get("present_creatures", []),
            "mood": text_node.get("mood", skeleton_node.get("mood", "tense")),
            "image_prompt": text_node.get("image_prompt", ""),
            "music_tone": text_node.get("music_tone", "mysterious"),
            "choices": text_node.get("choices", skeleton_node.get("choices", [])),
        }
        if "conditional_text" in text_node:
            merged["conditional_text"] = text_node["conditional_text"]
        if "endings" in skeleton_node:
            merged["endings"] = skeleton_node["endings"]
        return merged

    # ── metadata ────────────────────────────────────────────────────────

    @staticmethod
    def _make_artifact_id(data: dict[str, Any]) -> str:
        content = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"graph_{digest}"

    # ── sub-checkpoint helpers (Phase 5.6L) ────────────────────────────

    @staticmethod
    def _hash_dict(data: dict[str, Any]) -> str:
        """Compute a stable SHA256 hash of a dict for dependency tracking."""
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    async def _load_or_generate(
        store: Any,
        step: str,
        sub_id: str,
        dep_hash: str,
        fn: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Load from sub-checkpoint or generate + save.

        If a sub-checkpoint exists with a matching dependency hash,
        return it without regenerating. Otherwise, call fn(**kwargs),
        save the result, and return it.
        """
        if store is not None:
            cached = store.load_sub(step, sub_id, dep_hash)
            if cached is not None:
                return cached  # type: ignore[no-any-return]

        result = await fn(**kwargs)

        if store is not None:
            seed = kwargs.get("seed", 0)
            store.save_sub(step, sub_id, result, seed, dep_hash)

        return result  # type: ignore[no-any-return]
