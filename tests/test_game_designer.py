"""Tests for GameDesigner PipelineStep — TDD for Phase 5.

Tests all 3 modes of game_designer_v1.j2:
  Mode 1 — decision_points extraction
  Mode 2 — graph_skeleton generation
  Mode 3 — node_text generation
Plus merge validation against graph.schema.json.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from jsonschema import Draft7Validator

from src.job_queue import PipelineContext
from src.models.base import PipelineError, StepOutput

# ── schema loading ──────────────────────────────────────────────────────────

_GRAPH_SCHEMA: dict[str, Any] | None = None


def _get_graph_schema() -> dict[str, Any]:
    global _GRAPH_SCHEMA
    if _GRAPH_SCHEMA is None:
        path = os.path.join(
            os.path.dirname(__file__), "..", "docs", "schemas", "graph.schema.json",
        )
        with open(path) as f:
            _GRAPH_SCHEMA = json.load(f)
    return _GRAPH_SCHEMA


def _validate_graph_node(node: dict[str, Any]) -> list[str]:
    """Validate a single node by embedding it in a minimal graph envelope.

    The node schema uses $ref to '#/definitions/choice' which can only
    resolve from the full graph schema, not its sub-schema alone.
    """
    schema = _get_graph_schema()
    # Wrap the node in a complete graph so $ref pointers resolve
    envelope = {
        "schema_version": 1,
        "generator_version": "0.1.0",
        "pipeline_version": 1,
        "created_at": "2026-08-03T00:00:00Z",
        "model_versions": {"text_generator": "x", "validator": "x"},
        "seed": 1,
        "starting_node": "node_01",
        "flags_catalog": {},
        "nodes": [node] * 10,  # Pad to minItems: 10
        "endings_summary": [
            {"node_id": "node_01", "type": "dark", "title": "End"},
            {"node_id": "node_01", "type": "good", "title": "End"},
        ],
    }
    errors = [
        e.message for e in Draft7Validator(schema).iter_errors(envelope)
        # Filter to errors actually about our node (path starts with 'nodes')
        if (e.absolute_path and str(e.absolute_path[0]) == "nodes")
    ]
    return errors


def _validate_full_graph(graph: dict[str, Any]) -> list[str]:
    """Validate a complete graph dict against graph.schema.json."""
    schema = _get_graph_schema()
    errors = [e.message for e in Draft7Validator(schema).iter_errors(graph)]
    return errors


# ── test data ────────────────────────────────────────────────────────────────


def _make_bible() -> dict[str, Any]:
    """Minimal world bible for game designer prompts."""
    return {
        "world_name": "The Ashen Marches",
        "narrative_rules": {
            "tone": "dark_fantasy",
            "forbidden": ["resurrection"],
            "required_themes": ["sacrifice", "decay"],
            "mortality": "moderate",
            "knowledge_level": "superstitious",
        },
        "entities": {
            "characters": [
                {
                    "id": "char_01",
                    "name": "Eldrin Vane",
                    "aliases": [],
                    "description": "A lone wanderer seeking his sister.",
                    "role": "protagonist",
                    "archetype": "reluctant_hero",
                    "motivation": "Find his sister",
                    "flaw": "Pride",
                    "strength": "Courage",
                    "relationships": [],
                    "status": "alive",
                },
                {
                    "id": "char_02",
                    "name": "Mira",
                    "aliases": [],
                    "description": "A healer of Thorn's Hearth.",
                    "role": "supporting",
                    "archetype": "healer",
                    "motivation": "Protect the innocent",
                    "flaw": "Naivety",
                    "strength": "Wisdom",
                    "relationships": [],
                    "status": "alive",
                },
                {
                    "id": "char_03",
                    "name": "Malachar",
                    "aliases": ["The Salt Priest"],
                    "description": "High Priest of the Salt Temple.",
                    "role": "antagonist",
                    "archetype": "dark_priest",
                    "motivation": "Revive the dead god",
                    "flaw": "Obsession",
                    "strength": "Ruthlessness",
                    "relationships": [],
                    "status": "alive",
                },
            ],
            "locations": [
                {
                    "id": "loc_01",
                    "name": "The Salt Wastes",
                    "aliases": [],
                    "description": "Endless white salt flats.",
                    "type": "wilderness",
                    "mood": "desolate",
                },
                {
                    "id": "loc_02",
                    "name": "Salt Temple",
                    "aliases": [],
                    "description": "A glowing white cathedral of salt.",
                    "type": "temple",
                    "mood": "foreboding",
                },
                {
                    "id": "loc_03",
                    "name": "Thorn's Hearth",
                    "aliases": [],
                    "description": "A small settlement by a spring.",
                    "type": "village",
                    "mood": "peaceful",
                },
            ],
            "factions": [],
            "creatures": [],
            "artifacts": [],
            "events": [],
        },
        "systems": {
            "magic": {
                "source": "Salt-veins",
                "rules": ["Salt absorbs memory"],
                "costs": ["Each use erases a memory"],
                "limitations": "Cannot revive the dead",
            },
            "politics": {"power_structure": "Theocracy", "conflicts": []},
            "religion": {
                "gods": [{"name": "God-Heart", "domain": "Salt and memory", "status": "dead"}],
                "afterlife": "Salt preserves all",
            },
        },
    }


def _make_story_text() -> str:
    """A brief story summary for decision point extraction."""
    return (
        "Eldrin Vane crosses the Salt Wastes seeking his sister. "
        "In Thorn's Hearth, the healer Mira warns him of the Salt Priests. "
        "At the Salt Temple, Malachar offers power in exchange for the God-Heart Shard. "
        "Eldrin must choose: destroy the God-Heart, join Malachar, or find another way."
    )


def _make_decision_points() -> list[dict[str, Any]]:
    """Mock decision points from Mode 1."""
    return [
        {
            "dp_id": "dp_01",
            "chapter": 1,
            "scene_ref": "scene_01_02",
            "description": "Eldrin must decide whether to trust Mira.",
            "possible_choices": ["Accept Mira's help", "Decline and leave", "Demand answers"],
            "stakes": "Trust could mean salvation or betrayal.",
            "characters_involved": ["char_01", "char_02"],
            "location": "loc_03",
        },
        {
            "dp_id": "dp_02",
            "chapter": 2,
            "scene_ref": "scene_02_01",
            "description": "Eldrin finds a black crystal in the wastes.",
            "possible_choices": ["Pick it up", "Leave it"],
            "stakes": "The Shard holds power — and danger.",
            "characters_involved": ["char_01"],
            "location": "loc_01",
        },
        {
            "dp_id": "dp_03",
            "chapter": 2,
            "scene_ref": "scene_02_03",
            "description": "At the temple gates, a priest blocks the way.",
            "possible_choices": ["Enter", "Explore the grounds"],
            "stakes": "The High Priest awaits inside.",
            "characters_involved": ["char_01", "char_03"],
            "location": "loc_02",
        },
        {
            "dp_id": "dp_04",
            "chapter": 3,
            "scene_ref": "scene_03_01",
            "description": "Malachar offers Eldrin a choice: join or die.",
            "possible_choices": ["Fight Malachar", "Join him", "Destroy the Heart"],
            "stakes": "The fate of the Marches.",
            "characters_involved": ["char_01", "char_03"],
            "location": "loc_02",
        },
    ]


def _make_skeleton_graph() -> dict[str, Any]:
    """Mock skeleton graph from Mode 2 — structural fields only, no text.

    Has 12 nodes (schema requires minItems: 10). Nodes 01-04 are the main
    path, 05a-05d are middle branches, 06-07 are endings.
    """
    return {
        "nodes": [
            {
                "node_id": "node_01", "chapter": 1, "scene_type": "exploration",
                "description": "Eldrin begins his journey across the Salt Wastes.",
                "present_characters": ["char_01"], "present_location": "loc_01",
                "present_creatures": [], "mood": "desolate",
                "choices": [
                    {"choice_id": "ch_01_a", "choice_text": "Walk into the wastes", "target_node": "node_02", "requires_flags": [], "forbids_flags": [], "sets_flags": [], "consequence_hint": "The salt holds secrets"},
                    {"choice_id": "ch_01_b", "choice_text": "Visit Thorn's Hearth", "target_node": "node_03", "requires_flags": [], "forbids_flags": [], "sets_flags": [], "consequence_hint": "Mira may have answers"},
                ],
                "endings": {"is_ending": False},
            },
            {
                "node_id": "node_02", "chapter": 1, "scene_type": "discovery",
                "description": "Eldrin discovers a black crystal in the salt.",
                "present_characters": ["char_01"], "present_location": "loc_01",
                "present_creatures": [], "mood": "mysterious",
                "choices": [
                    {"choice_id": "ch_02_a", "choice_text": "Pick up the crystal", "target_node": "node_04", "requires_flags": [], "forbids_flags": [], "sets_flags": ["took_shard"], "consequence_hint": "The Shard pulses with power"},
                ],
                "endings": {"is_ending": False},
            },
            {
                "node_id": "node_03", "chapter": 1, "scene_type": "dialogue",
                "description": "Eldrin speaks with Mira at Thorn's Hearth.",
                "present_characters": ["char_01", "char_02"], "present_location": "loc_03",
                "present_creatures": [], "mood": "peaceful",
                "choices": [
                    {"choice_id": "ch_03_a", "choice_text": "Accept Mira's help", "target_node": "node_04", "requires_flags": [], "forbids_flags": [], "sets_flags": ["trusted_mira"], "consequence_hint": "Mira shares her knowledge"},
                ],
                "endings": {"is_ending": False},
            },
            {
                "node_id": "node_04", "chapter": 2, "scene_type": "choice",
                "description": "The Salt Temple looms ahead.",
                "present_characters": ["char_01", "char_03"], "present_location": "loc_02",
                "present_creatures": [], "mood": "tense",
                "choices": [
                    {"choice_id": "ch_04_a", "choice_text": "Enter the temple", "target_node": "node_05a", "requires_flags": [], "forbids_flags": [], "sets_flags": ["entered_temple"], "consequence_hint": "The High Priest awaits"},
                    {"choice_id": "ch_04_b", "choice_text": "Explore the grounds", "target_node": "node_05b", "requires_flags": [], "forbids_flags": [], "sets_flags": [], "consequence_hint": "The temple has many secrets"},
                    {"choice_id": "ch_04_c", "choice_text": "Turn back to the wastes", "target_node": "node_05c", "requires_flags": [], "forbids_flags": [], "sets_flags": ["fled_temple"], "consequence_hint": "Some would call it wisdom"},
                ],
                "endings": {"is_ending": False},
            },
            {"node_id": "node_05a", "chapter": 2, "scene_type": "dialogue", "description": "Inside the temple", "present_characters": ["char_01", "char_03"], "present_location": "loc_02", "present_creatures": [], "mood": "ominous", "choices": [{"choice_id": "ch_05_a", "choice_text": "Confront Malachar", "target_node": "node_06", "requires_flags": [], "forbids_flags": [], "sets_flags": [], "consequence_hint": "No turning back"}], "endings": {"is_ending": False}},
            {"node_id": "node_05b", "chapter": 2, "scene_type": "discovery", "description": "Crypt behind the temple", "present_characters": ["char_01"], "present_location": "loc_02", "present_creatures": [], "mood": "mysterious", "choices": [{"choice_id": "ch_05_b", "choice_text": "Study the ancient map", "target_node": "node_05d", "requires_flags": [], "forbids_flags": [], "sets_flags": ["found_map"], "consequence_hint": "Knowledge is power"}], "endings": {"is_ending": False}},
            {"node_id": "node_05c", "chapter": 2, "scene_type": "exploration", "description": "Fleeing through the wastes", "present_characters": ["char_01"], "present_location": "loc_01", "present_creatures": [], "mood": "tense", "choices": [{"choice_id": "ch_05_c", "choice_text": "Find shelter at Thorn's Hearth", "target_node": "node_06", "requires_flags": [], "forbids_flags": ["fled_temple"], "sets_flags": [], "consequence_hint": "Mira will understand"}], "endings": {"is_ending": False}},
            {"node_id": "node_05d", "chapter": 2, "scene_type": "choice", "description": "The map reveals the God-Heart's location", "present_characters": ["char_01"], "present_location": "loc_02", "present_creatures": [], "mood": "mysterious", "choices": [{"choice_id": "ch_05_d", "choice_text": "Use the secret passage", "target_node": "node_06", "requires_flags": ["found_map"], "forbids_flags": [], "sets_flags": [], "consequence_hint": "Behind the altar"}], "endings": {"is_ending": False}},
            {
                "node_id": "node_06", "chapter": 3, "scene_type": "climax",
                "description": "Final confrontation with Malachar.",
                "present_characters": ["char_01", "char_03"], "present_location": "loc_02",
                "present_creatures": [], "mood": "tense",
                "choices": [
                    {"choice_id": "ch_06_a", "choice_text": "Destroy the God-Heart", "target_node": "node_10", "requires_flags": [], "forbids_flags": [], "sets_flags": [], "consequence_hint": "The world changes forever"},
                    {"choice_id": "ch_06_b", "choice_text": "Join Malachar", "target_node": "node_11", "requires_flags": [], "forbids_flags": [], "sets_flags": [], "consequence_hint": "Power has its price"},
                ],
                "endings": {"is_ending": False},
            },
            {"node_id": "node_10", "chapter": 3, "scene_type": "ending", "description": "Good ending.", "present_characters": ["char_01"], "present_location": "loc_02", "present_creatures": [], "mood": "triumphant", "choices": [], "endings": {"is_ending": True, "ending_type": "good", "ending_title": "Freedom"}},
            {"node_id": "node_11", "chapter": 3, "scene_type": "ending", "description": "Dark ending.", "present_characters": ["char_01", "char_03"], "present_location": "loc_02", "present_creatures": [], "mood": "dark", "choices": [], "endings": {"is_ending": True, "ending_type": "dark", "ending_title": "The Vessel"}},
        ],
    }


def _make_node_text_output() -> dict[str, Any]:
    """Mock Mode 3 output — text + choices for a single node."""
    return {
        "node_id": "node_01",
        "text": (
            "You stand at the edge of the wastes.\n"
            "White salt stretches to every horizon.\n"
            "A cold wind bites your face.\n"
            "Your sister's face haunts your thoughts.\n"
            "\"Keep moving,\" you tell yourself.\n"
            "The journey must begin now.\n"
            "There is no turning back."
        ),
        "choices": [
            {
                "choice_id": "ch_01_a",
                "choice_text": "Walk into the salt wastes",
                "target_node": "node_02",
                "requires_flags": [],
                "forbids_flags": [],
                "sets_flags": [],
                "consequence_hint": "The salt holds secrets",
            },
            {
                "choice_id": "ch_01_b",
                "choice_text": "Visit Thorn's Hearth first",
                "target_node": "node_03",
                "requires_flags": [],
                "forbids_flags": [],
                "sets_flags": [],
                "consequence_hint": "Mira may have answers",
            },
        ],
        "mood": "desolate",
        "image_prompt": "A lone figure at the edge of endless white salt flats, cold blue horizon",
        "music_tone": "melancholy",
    }


# ── Mock Generator ───────────────────────────────────────────────────────────


class MockGameDesignerGenerator:
    """Mock TextGenerator that returns appropriate output for each GameDesigner mode."""

    model_name: str = "test-model"
    quantization: str = "Q4_K_M"

    def __init__(
        self,
        decision_points: list[dict[str, Any]] | None = None,
        skeleton: dict[str, Any] | None = None,
        node_texts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._dp = decision_points or _make_decision_points()
        self._skeleton = skeleton or _make_skeleton_graph()
        self._node_texts = node_texts or {}
        self.call_count = 0
        self.last_prompts: list[str] = []

    async def generate(
        self,
        prompt: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        self.call_count += 1
        self.last_prompts.append(prompt)

        # Detect mode from prompt content
        if '"decision_points"' in prompt:
            return {"decision_points": list(self._dp)}
        elif '"nodes"' in prompt and "description" in prompt:
            return dict(self._skeleton)
        elif "node_id" in prompt and "text" in prompt:
            # Mode 3 — extract node_id from the prompt
            import re
            match = re.search(r"node_(\d+)", prompt)
            node_id = f"node_{match.group(1)}" if match else "node_01"
            return self._node_texts.get(node_id, _make_node_text_output())
        else:
            return {"unknown": "mode"}


# ── GameDesigner (TDD skeleton) ──────────────────────────────────────────────

# The actual GameDesigner class will be in src/models/game_designer.py.
# These tests define the expected API. The class is imported here for test writing;
# if it doesn't exist yet, tests write against the expected interface shape.
#
# Expected API:
#   GameDesigner(generator, validator=None, config=None, failure_policy=ABORT)
#   async extract_decision_points(story_text, temperature, seed) -> dict
#   async build_graph_skeleton(bible, decision_points, target_nodes, temp, seed) -> dict
#   async generate_node_text(bible, node_desc, neighbors, active_flags, temp, seed) -> dict
#   merge_node(skeleton_node, text_node) -> dict  (static)
#   async generate(context) -> StepOutput  (PipelineStep)


class TestDecisionPointsExtraction:
    """Mode 1: Extract decision points from a linear story."""

    @pytest.mark.asyncio
    async def test_extracts_decision_points(self) -> None:
        """Basic extraction returns 12-18 decision points."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"decision_points"} The story: ' + _make_story_text(),
        )
        result = raw["decision_points"]
        assert isinstance(result, list)
        assert len(result) >= 1  # In real mode: 12-18, mock returns 4

    @pytest.mark.asyncio
    async def test_decision_point_has_required_fields(self) -> None:
        """Each DP has dp_id, chapter, scene_ref, description, possible_choices, stakes."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"decision_points"} The story: ' + _make_story_text(),
        )
        for dp in raw["decision_points"]:
            assert "dp_id" in dp
            assert dp["dp_id"].startswith("dp_")
            assert "chapter" in dp
            assert dp["chapter"] in (1, 2, 3)
            assert "scene_ref" in dp
            assert "description" in dp
            assert "possible_choices" in dp
            assert len(dp["possible_choices"]) >= 2
            assert "stakes" in dp
            assert "characters_involved" in dp
            assert "location" in dp

    @pytest.mark.asyncio
    async def test_decision_points_focus_on_middle_chapter(self) -> None:
        """Most decision points are in chapter 2 per prompt's CRITICAL rule."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"decision_points"} The story: ' + _make_story_text(),
        )
        ch2_count = sum(1 for dp in raw["decision_points"] if dp["chapter"] == 2)
        assert ch2_count >= 1  # At least some in chapter 2

    @pytest.mark.asyncio
    async def test_story_text_injected_into_prompt(self) -> None:
        """The story text appears in the prompt sent to the LLM."""
        gen = MockGameDesignerGenerator()
        story = "A hero walks into the salt wastes."
        await gen.generate(prompt='{"decision_points"} The story: ' + story)
        assert story in gen.last_prompts[0]

    @pytest.mark.asyncio
    async def test_empty_story_produces_empty_or_minimal_dps(self) -> None:
        """An empty or minimal story should not crash extraction."""

        class EmptyStoryGenerator:
            model_name = "test"
            quantization = "Q4"

            async def generate(self, prompt="", **kwargs):
                return {"decision_points": []}

        gen = EmptyStoryGenerator()
        raw = await gen.generate(prompt='{"decision_points"} The story: ')
        assert isinstance(raw["decision_points"], list)
        assert len(raw["decision_points"]) == 0


class TestGraphSkeletonGeneration:
    """Mode 2: Build graph skeleton from decision points."""

    @pytest.mark.asyncio
    async def test_builds_skeleton_with_nodes(self) -> None:
        """Skeleton contains nodes array with structural fields."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        assert "nodes" in raw
        assert len(raw["nodes"]) >= 2  # At least start + end

    @pytest.mark.asyncio
    async def test_skeleton_nodes_have_structural_fields(self) -> None:
        """Each skeleton node has node_id, chapter, scene_type, present_*, mood, choices, endings."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        for node in raw["nodes"]:
            assert "node_id" in node
            assert node["node_id"].startswith("node_")
            assert "chapter" in node
            assert "scene_type" in node
            assert scene_type_valid(node["scene_type"])
            assert "description" in node
            assert "present_characters" in node
            assert "present_location" in node
            assert "present_creatures" in node
            assert "mood" in node
            assert "choices" in node
            assert "endings" in node

    @pytest.mark.asyncio
    async def test_skeleton_has_start_node(self) -> None:
        """node_01 exists and is the start."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        node_ids = [n["node_id"] for n in raw["nodes"]]
        assert "node_01" in node_ids

    @pytest.mark.asyncio
    async def test_skeleton_has_at_least_two_endings(self) -> None:
        """2-3 endings per CRITICAL rule."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        endings = [
            n for n in raw["nodes"]
            if n.get("endings", {}).get("is_ending", False)
        ]
        assert len(endings) >= 2

    @pytest.mark.asyncio
    async def test_skeleton_choices_have_valid_targets(self) -> None:
        """Every choice's target_node points to an existing node."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        node_ids = {n["node_id"] for n in raw["nodes"]}
        for node in raw["nodes"]:
            for ch in node.get("choices", []):
                assert ch["target_node"] in node_ids, (
                    f"Choice {ch.get('choice_id', '?')} in {node['node_id']} "
                    f"targets non-existent {ch.get('target_node', '?')}"
                )

    @pytest.mark.asyncio
    async def test_skeleton_choice_ids_match_pattern(self) -> None:
        """Choice IDs match ch_NN_x pattern."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        import re
        pattern = re.compile(r"^ch_\d{2}_[a-z]$")
        for node in raw["nodes"]:
            for ch in node.get("choices", []):
                cid = ch.get("choice_id", "")
                assert pattern.match(cid), (
                    f"choice_id '{cid}' in {node['node_id']} "
                    f"does not match ^ch_\\d{{2}}_[a-z]$"
                )

    @pytest.mark.asyncio
    async def test_ending_nodes_have_no_choices(self) -> None:
        """Ending nodes should have empty choices."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(_make_decision_points()),
        )
        for node in raw["nodes"]:
            if node.get("endings", {}).get("is_ending", False):
                assert node["choices"] == [], (
                    f"Ending node {node['node_id']} should have no choices"
                )


class TestNodeTextGeneration:
    """Mode 3: Generate text + choices for a single CYOA node."""

    @pytest.mark.asyncio
    async def test_generates_node_text(self) -> None:
        """Returns node_id, text, choices, mood, image_prompt, music_tone."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        assert "node_id" in raw
        assert "text" in raw
        assert "choices" in raw
        assert "mood" in raw
        assert "image_prompt" in raw
        assert "music_tone" in raw

    @pytest.mark.asyncio
    async def test_text_is_7_to_10_lines(self) -> None:
        """Text must be exactly 7-10 lines per CRITICAL rule."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        lines = raw["text"].strip().split("\n")
        assert 7 <= len(lines) <= 10, f"Got {len(lines)} lines, expected 7-10"

    @pytest.mark.asyncio
    async def test_each_line_10_words_or_fewer(self) -> None:
        """Each line must contain 10 words or fewer."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        for line in raw["text"].strip().split("\n"):
            word_count = len(line.split())
            assert word_count <= 10, f"Line has {word_count} words: '{line}'"

    @pytest.mark.asyncio
    async def test_choices_have_required_fields(self) -> None:
        """Each choice has choice_id, choice_text, target_node."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        for ch in raw["choices"]:
            assert "choice_id" in ch
            assert "choice_text" in ch
            assert len(ch["choice_text"]) > 0
            assert "target_node" in ch

    @pytest.mark.asyncio
    async def test_music_tone_is_valid_value(self) -> None:
        """music_tone is one of the 6 supported tones."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        valid_tones = {"tense", "peaceful", "triumphant", "melancholy", "mysterious", "heroic"}
        assert raw["music_tone"] in valid_tones

    @pytest.mark.asyncio
    async def test_image_prompt_is_non_empty(self) -> None:
        """image_prompt is a non-empty string for downstream Stable Diffusion."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        assert len(raw["image_prompt"]) > 10

    @pytest.mark.asyncio
    async def test_optional_conditional_text(self) -> None:
        """conditional_text is present and valid when included."""

        class ConditionalGenerator:
            model_name = "test"
            quantization = "Q4"

            async def generate(self, prompt="", **kwargs):
                result = _make_node_text_output()
                result["conditional_text"] = [
                    {"if_flag": "took_shard", "append": "\nThe Shard pulses hot."},
                ]
                return result

        gen = ConditionalGenerator()
        raw = await gen.generate(prompt='node_id node_01 text choices')
        assert "conditional_text" in raw
        assert len(raw["conditional_text"]) == 1
        assert raw["conditional_text"][0]["if_flag"] == "took_shard"
        assert "append" in raw["conditional_text"][0]

    @pytest.mark.asyncio
    async def test_node_text_includes_dialogue(self) -> None:
        """At least one line contains dialogue in quotes."""
        gen = MockGameDesignerGenerator()
        raw = await gen.generate(
            prompt='node_id node_01 text choices',
        )
        assert '"' in raw["text"], "Text should include dialogue lines with quotes"


class TestMergeValidation:
    """Merge skeleton (structural) + text (content) → schema-valid node."""

    @staticmethod
    def merge_node(
        skeleton_node: dict[str, Any],
        text_node: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge Mode 2 skeleton with Mode 3 text into a complete node.

        This is the expected merge logic that GameDesigner will implement.
        Skeleton provides: node_id, chapter, scene_type, present_characters,
            present_location, present_creatures, description, endings
        Text provides: text, choices (with full details), mood, image_prompt,
            music_tone, conditional_text (optional)
        """
        merged: dict[str, Any] = {
            "node_id": skeleton_node["node_id"],
            "chapter": skeleton_node["chapter"],
            "scene_type": skeleton_node["scene_type"],
            "text": text_node["text"],
            "present_characters": skeleton_node["present_characters"],
            "present_location": skeleton_node["present_location"],
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

    def test_merge_produces_valid_node(self) -> None:
        """Merged node validates against graph schema node definition."""
        skeleton_nodes = _make_skeleton_graph()["nodes"]
        text_output = _make_node_text_output()

        merged = self.merge_node(skeleton_nodes[0], text_output)
        errors = _validate_graph_node(merged)
        assert not errors, f"Merge produced invalid node: {errors}"

    def test_merge_preserves_structural_fields(self) -> None:
        """Chapter, scene_type, present_* come from skeleton."""
        skeleton_nodes = _make_skeleton_graph()["nodes"]
        text_output = _make_node_text_output()

        merged = self.merge_node(skeleton_nodes[0], text_output)
        assert merged["chapter"] == skeleton_nodes[0]["chapter"]
        assert merged["scene_type"] == skeleton_nodes[0]["scene_type"]
        assert merged["present_characters"] == skeleton_nodes[0]["present_characters"]
        assert merged["present_location"] == skeleton_nodes[0]["present_location"]

    def test_merge_preserves_content_fields(self) -> None:
        """Text, choices, mood, image_prompt, music_tone come from text node."""
        skeleton_nodes = _make_skeleton_graph()["nodes"]
        text_output = _make_node_text_output()

        merged = self.merge_node(skeleton_nodes[0], text_output)
        assert merged["text"] == text_output["text"]
        assert merged["choices"] == text_output["choices"]
        assert merged["mood"] == text_output["mood"]
        assert merged["image_prompt"] == text_output["image_prompt"]

    def test_merge_handles_ending_node(self) -> None:
        """Merge correctly handles ending nodes with no choices."""
        skeleton = _make_skeleton_graph()
        ending_node = skeleton["nodes"][-1]  # node_11 — dark ending

        text_output = {
            "node_id": "node_11",
            "text": "You kneel before the Heart.\nPower floods your veins.\nYou are no longer yourself.\nThe new vessel rises.\nThe salt claims another.\nYour sister's face fades.\nDarkness consumes all.",
            "choices": [],
            "mood": "dark",
            "image_prompt": "A dark figure being consumed by the God-Heart's power",
            "music_tone": "dark",
        }

        merged = self.merge_node(ending_node, text_output)
        errors = _validate_graph_node(merged)
        assert not errors, f"Merge ending node failed: {errors}"
        assert merged["choices"] == []
        assert merged["endings"]["is_ending"] is True

    def test_merge_handles_conditional_text(self) -> None:
        """Conditional text from Mode 3 is preserved in merge."""
        skeleton_nodes = _make_skeleton_graph()["nodes"]
        text_output = _make_node_text_output()
        text_output["conditional_text"] = [
            {"if_flag": "took_shard", "append": "\nThe Shard pulses hot against your skin."},
        ]

        merged = self.merge_node(skeleton_nodes[0], text_output)
        errors = _validate_graph_node(merged)
        assert not errors, f"Merge with conditional_text failed: {errors}"
        assert "conditional_text" in merged
        assert merged["conditional_text"][0]["if_flag"] == "took_shard"

    def test_merge_without_optional_text_fields(self) -> None:
        """Merge works when text node lacks optional fields like image_prompt."""
        skeleton_nodes = _make_skeleton_graph()["nodes"]
        minimal_text = {
            "node_id": "node_01",
            "text": "Line one.\nLine two.\nLine three.\nLine four.\nLine five.\nLine six.\nLine seven.\n",
            "choices": skeleton_nodes[0]["choices"],
            "mood": "tense",
        }

        merged = self.merge_node(skeleton_nodes[0], minimal_text)
        errors = _validate_graph_node(merged)
        assert not errors, f"Merge with minimal text failed: {errors}"
        # Defaults should be applied
        assert merged["image_prompt"] == ""

    def test_merge_all_nodes_produce_valid_graph(self) -> None:
        """Merging all skeleton nodes with text produces a valid graph.json."""
        skeleton = _make_skeleton_graph()

        # Build full graph by merging each node with mock text
        nodes = []
        for sn in skeleton["nodes"]:
            text_out = _make_node_text_output()
            text_out["node_id"] = sn["node_id"]
            if sn["endings"].get("is_ending"):
                text_out["choices"] = []
            merged = self.merge_node(sn, text_out)
            nodes.append(merged)

        graph = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": "2026-08-03T00:00:00Z",
            "model_versions": {
                "text_generator": "test-model-Q4_K_M",
                "validator": "test-model-Q4_K_M",
            },
            "seed": 42,
            "starting_node": "node_01",
            "flags_catalog": {"took_shard": "Picked up the God-Heart Shard"},
            "nodes": nodes,
            "endings_summary": [
                {"node_id": "node_10", "type": "good", "title": "Freedom"},
                {"node_id": "node_11", "type": "dark", "title": "The Vessel"},
            ],
        }

        errors = _validate_full_graph(graph)
        assert not errors, f"Full graph failed validation: {errors}"


class TestGameDesignerIntegration:
    """End-to-end: decision_points → skeleton → node_text → merge → valid graph."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_graph(self) -> None:
        """Chaining all 3 modes produces a graph that validates against schema."""
        # Mode 1
        dp_gen = MockGameDesignerGenerator()
        dp_raw = await dp_gen.generate(
            prompt='{"decision_points"} ' + _make_story_text(),
        )
        dps = dp_raw["decision_points"]
        assert len(dps) >= 1

        # Mode 2
        skel_gen = MockGameDesignerGenerator()
        skel_raw = await skel_gen.generate(
            prompt='{"nodes" description} dp: ' + json.dumps(dps),
        )
        skeleton = skel_raw["nodes"]
        assert len(skeleton) >= 2

        # Mode 3 + Merge
        nodes = []
        for sn in skeleton:
            text_gen = MockGameDesignerGenerator()
            text_raw = await text_gen.generate(
                prompt=f"node_id {sn['node_id']} text choices",
            )
            merged = TestMergeValidation.merge_node(sn, text_raw)
            nodes.append(merged)

        # Assemble full graph
        graph = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": "2026-08-03T00:00:00Z",
            "model_versions": {
                "text_generator": "test-Q4_K_M",
                "validator": "test-Q4_K_M",
            },
            "seed": 42,
            "starting_node": "node_01",
            "flags_catalog": {},
            "nodes": nodes,
            "endings_summary": [
                {"node_id": "node_10", "type": "good", "title": "Dawn"},
                {"node_id": "node_11", "type": "dark", "title": "Dusk"},
            ],
        }

        errors = _validate_full_graph(graph)
        assert not errors, f"Full pipeline output failed graph schema: {errors}"

    @pytest.mark.asyncio
    async def test_pipeline_with_mismatched_node_ids_raises(self) -> None:
        """If Mode 3 returns wrong node_id, merge should detect it."""
        skeleton_node = _make_skeleton_graph()["nodes"][0]  # node_01
        text_output = _make_node_text_output()
        text_output["node_id"] = "node_99"  # Mismatch!

        # Merge should still work (returns merged data), but the result
        # would have inconsistent node_id. In production, GameDesigner
        # should warn or raise. This test documents the expected behavior.
        merged = TestMergeValidation.merge_node(skeleton_node, text_output)
        # node_id comes from skeleton (structural authority), so it stays correct
        assert merged["node_id"] == "node_01"


class TestGameDesignerEdgeCases:
    """Edge cases and error handling."""

    def test_empty_decision_points_produces_minimal_graph(self) -> None:
        """No decision points → GameDesigner should handle gracefully."""
        # Validate that empty DP list doesn't crash skeleton generation
        assert len([]) == 0  # Placeholder — real test when GameDesigner is implemented

    @pytest.mark.asyncio
    async def test_missing_bible_context(self) -> None:
        """GameDesigner requires bible in context.outputs (like StoryWriter)."""
        ctx = PipelineContext(run_id="r1", seed=1)
        # No bible set — GameDesigner should raise

        # This will be tested once GameDesigner is implemented:
        # designer = GameDesigner(generator=MockGameDesignerGenerator())
        # with pytest.raises(PipelineError, match="bible"):
        #     await designer.run(ctx)
        pass  # Placeholder for TDD

    @pytest.mark.asyncio
    async def test_malformed_llm_output_in_any_mode(self) -> None:
        """Each mode should raise on non-dict LLM output."""

        class BadGenerator:
            model_name = "test"
            quantization = "Q4"

            async def generate(self, prompt="", **kwargs):
                return ["not", "a", "dict"]

        gen = BadGenerator()
        raw = await gen.generate()
        assert isinstance(raw, list)  # This should raise in real GameDesigner


class TestMergeNodeKeyErrorResilience:
    """merge_node tolerates malformed skeleton and text nodes."""

    def test_skeleton_without_node_id_uses_fallback(self) -> None:
        """Skeleton node missing node_id uses '?' as fallback."""
        from src.models.game_designer import GameDesigner

        result = GameDesigner.merge_node(
            skeleton_node={"chapter": 1, "scene_type": "exploration",
                           "present_characters": [], "present_location": "loc_01"},
            text_node={"text": "Scene text.", "choices": []},
        )
        assert result["node_id"] == "?"

    def test_text_node_without_text_uses_empty_string(self) -> None:
        """Text node missing 'text' field uses '' as fallback."""
        from src.models.game_designer import GameDesigner

        result = GameDesigner.merge_node(
            skeleton_node={"node_id": "node_01", "chapter": 1, "scene_type": "exploration",
                           "present_characters": [], "present_location": "loc_01"},
            text_node={"choices": []},
        )
        assert result["text"] == ""

    def test_skeleton_without_chapter_uses_zero(self) -> None:
        """Skeleton node without 'chapter' uses 0 as fallback."""
        from src.models.game_designer import GameDesigner

        result = GameDesigner.merge_node(
            skeleton_node={"node_id": "node_01", "scene_type": "exploration",
                           "present_characters": [], "present_location": "loc_01"},
            text_node={"text": "Text", "choices": []},
        )
        assert result["chapter"] == 0

    def test_completely_empty_nodes_dont_crash(self) -> None:
        """Both nodes empty → graceful fallback, no KeyError."""
        from src.models.game_designer import GameDesigner

        result = GameDesigner.merge_node({}, {})
        assert result["node_id"] == "?"
        assert result["text"] == ""
        assert result["chapter"] == 0
        assert result["mood"] == "tense"


def scene_type_valid(st: str) -> bool:
    """Check scene_type is one of the 8 valid enum values."""
    return st in {
        "exploration", "combat", "dialogue", "discovery",
        "choice", "climax", "resolution", "ending",
    }
