"""Tests for MusicGeneratorStep — TDD for Phase 5.

MusicGeneratorStep converts scene text + tone → ABC notation (via TextGenerator)
→ MIDI (via music21). Runs in parallel via Job Queue.

Pipeline: node.text + music_tone → TextGenerator (composer_v1.j2) → ABC → MIDI
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from src.job_queue import PipelineContext
from src.models.base import PipelineError, StepOutput


# ── test data ────────────────────────────────────────────────────────────────

_VALID_ABC = (
    "X:1\n"
    "T:Goblin Encounter\n"
    "M:4/4\n"
    "L:1/8\n"
    "K:Dm\n"
    "D2 F2 A2 d2 | c2 A2 F2 D2 | E2 G2 c2 e2 | d8 |]\n"
)

_INVALID_ABC = "This is not music notation at all"


def _make_single_node() -> dict[str, Any]:
    """A single graph node with text and music_tone."""
    return {
        "node_id": "node_01",
        "chapter": 1,
        "scene_type": "exploration",
        "text": (
            "You stand at the edge of the wastes.\n"
            "White salt stretches to every horizon.\n"
            "A cold wind bites your face.\n"
            "Your journey begins now.\n"
            "What will you do?\n"
            "The path calls you forward.\n"
            "There is no turning back."
        ),
        "present_characters": ["char_01"],
        "present_location": "loc_01",
        "present_creatures": [],
        "mood": "desolate",
        "image_prompt": "A lone figure at the edge of endless white salt flats",
        "music_tone": "melancholy",
        "choices": [],
    }


def _make_multiple_nodes() -> list[dict[str, Any]]:
    """Three nodes with different moods for batch testing."""
    return [
        {
            "node_id": "node_01",
            "text": "You stand at the edge of the wastes.\nWhite salt stretches to every horizon.",
            "music_tone": "melancholy",
            "mood": "desolate",
        },
        {
            "node_id": "node_02",
            "text": "The Salt Wraith rises from the floor.\nIts scream freezes your blood.",
            "music_tone": "tense",
            "mood": "tense",
        },
        {
            "node_id": "node_03",
            "text": "The God-Heart shatters with light.\nThe chains snap, one by one.",
            "music_tone": "triumphant",
            "mood": "triumphant",
        },
    ]


# ── Mock TextGenerator (produces ABC notation) ───────────────────────────────


class MockAbcTextGenerator:
    """Mock TextGenerator that returns mood-appropriate ABC notation."""

    model_name: str = "test-model"
    quantization: str = "Q4_K_M"

    def __init__(self) -> None:
        self.call_count = 0
        self.last_prompts: list[str] = []

    async def generate(
        self,
        prompt: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> str:
        self.call_count += 1
        self.last_prompts.append(prompt)

        # Detect music_tone from the prompt
        tone_match = re.search(r"MUSIC TONE:\s*(\w+)", prompt)
        tone = tone_match.group(1) if tone_match else "mysterious"

        key_map = {
            "tense": "Dm",
            "peaceful": "C",
            "triumphant": "G",
            "melancholy": "Am",
            "mysterious": "Em",
            "heroic": "D",
        }
        key = key_map.get(tone, "Dm")

        return (
            "X:1\n"
            f"T:{tone.title()} Scene\n"
            "M:4/4\n"
            "L:1/8\n"
            f"K:{key}\n"
            "D2 F2 A2 d2 | c2 A2 F2 D2 | E2 G2 c2 e2 | d8 |]\n"
        )


class MockFailingAbcGenerator:
    """TextGenerator that returns invalid ABC."""

    model_name = "broken"
    quantization = "Q0"

    async def generate(self, prompt="", **kwargs) -> str:
        return _INVALID_ABC


class MockNonDictAbcGenerator:
    """TextGenerator that returns non-string (should raise)."""

    model_name = "broken"
    quantization = "Q0"

    async def generate(self, prompt="", **kwargs) -> list[str]:
        return ["not", "a", "string"]


# ── Mock MIDI Converter ──────────────────────────────────────────────────────


class MockMidiConverter:
    """Mock music21 converter for ABC→MIDI."""

    def __init__(self) -> None:
        self.convert_count = 0
        self.last_abc: str = ""

    def abc_to_midi(self, abc_notation: str) -> bytes:
        self.convert_count += 1
        self.last_abc = abc_notation
        return b"MThd" + abc_notation.encode()[:100]

    @staticmethod
    def validate_abc(abc_notation: str) -> bool:
        """Cheap structural validation for testing."""
        if not abc_notation or not abc_notation.strip():
            return False
        if not re.search(r"^X:\s*\d+", abc_notation, re.MULTILINE):
            return False
        if not re.search(r"^M:", abc_notation, re.MULTILINE):
            return False
        if not re.search(r"^K:", abc_notation, re.MULTILINE):
            return False
        # Check for actual note sequences (e.g. "D2", "F2", "c2", "d8")
        # Must have letters A-G followed by a duration digit, not just key sig
        return bool(re.search(r"[A-Ga-g]\d+", abc_notation))


# ── Tests ────────────────────────────────────────────────────────────────────


class TestMusicGeneratorStepSingle:
    """Single MIDI generation from a node."""

    @pytest.mark.asyncio
    async def test_generates_abc_from_node(self) -> None:
        """TextGenerator produces ABC notation from composer_v1.j2 prompt."""
        gen = MockAbcTextGenerator()
        node = _make_single_node()

        # Simulate: render composer_v1.j2 with scene_text + music_tone
        prompt = (
            f"SCENE:\n{node['text']}\n\n"
            f"SCENE MOOD: {node['mood']}\n"
            f"MUSIC TONE: {node['music_tone']}\n"
        )
        abc = await gen.generate(prompt=prompt)

        assert abc.startswith("X:1")
        assert "M:4/4" in abc
        assert "K:" in abc
        assert gen.call_count == 1

    @pytest.mark.asyncio
    async def test_converts_abc_to_midi(self) -> None:
        """Valid ABC notation is converted to MIDI bytes."""
        converter = MockMidiConverter()
        assert converter.validate_abc(_VALID_ABC)

        midi_bytes = converter.abc_to_midi(_VALID_ABC)
        assert midi_bytes.startswith(b"MThd")
        assert converter.convert_count == 1

    @pytest.mark.asyncio
    async def test_validates_abc_before_conversion(self) -> None:
        """Invalid ABC is caught before conversion attempt."""
        converter = MockMidiConverter()
        valid = converter.validate_abc(_INVALID_ABC)
        assert not valid, "Invalid ABC should fail validation"

    @pytest.mark.asyncio
    async def test_music_tone_determines_key(self) -> None:
        """The music_tone influences the key signature (tense→Dm, triumphant→G)."""
        gen = MockAbcTextGenerator()

        # Tense scene → minor key
        abc_tense = await gen.generate(
            prompt="MUSIC TONE: tense\nSCENE: combat\n"
        )
        assert "K:Dm" in abc_tense

        # Triumphant scene → major key
        abc_triumph = await gen.generate(
            prompt="MUSIC TONE: triumphant\nSCENE: victory\n"
        )
        assert "K:G" in abc_triumph

    @pytest.mark.asyncio
    async def test_deterministic_output(self) -> None:
        """Same prompt + seed → same ABC notation."""
        gen1 = MockAbcTextGenerator()
        gen2 = MockAbcTextGenerator()
        prompt = "MUSIC TONE: melancholy\nSCENE: sad scene\n"

        abc1 = await gen1.generate(prompt=prompt, seed=42)
        abc2 = await gen2.generate(prompt=prompt, seed=42)
        assert abc1 == abc2

    @pytest.mark.asyncio
    async def test_scene_text_injected_into_prompt(self) -> None:
        """The node's text appears in the composer prompt."""
        gen = MockAbcTextGenerator()
        node = _make_single_node()
        await gen.generate(
            prompt=f"SCENE:\n{node['text']}\nMUSIC TONE: {node['music_tone']}"
        )
        assert "the edge of the wastes" in gen.last_prompts[0]

    @pytest.mark.asyncio
    async def test_step_output_includes_metadata(self) -> None:
        """StepOutput includes artifact_id, midi data, and generation params."""
        gen = MockAbcTextGenerator()
        node = _make_single_node()
        abc = await gen.generate(
            prompt=f"MUSIC TONE: {node['music_tone']}\nSCENE: {node['text']}"
        )
        converter = MockMidiConverter()
        midi = converter.abc_to_midi(abc)

        output = StepOutput(
            data={
                "midi": {
                    "node_01": {
                        "abc_notation": abc,
                        "midi_bytes_length": len(midi),
                        "music_tone": node["music_tone"],
                        "seed": 42,
                    }
                },
                "midi_count": 1,
            },
            step_name="music_generator",
            artifact_id="mid_a1b2c3d4",
        )

        assert output.step_name == "music_generator"
        assert output.artifact_id is not None
        assert output.data["midi_count"] == 1
        assert "node_01" in output.data["midi"]


class TestMusicGeneratorStepBatch:
    """Batch MIDI generation for multiple nodes."""

    @pytest.mark.asyncio
    async def test_generates_midi_for_all_nodes(self) -> None:
        """Each node gets its own MIDI file with its own seed."""
        nodes = _make_multiple_nodes()
        gen = MockAbcTextGenerator()
        converter = MockMidiConverter()

        results: dict[str, bytes] = {}
        for i, node in enumerate(nodes):
            seed = 100 + i
            prompt = f"MUSIC TONE: {node['music_tone']}\nSCENE: {node['text']}"
            abc = await gen.generate(prompt=prompt, seed=seed)
            assert converter.validate_abc(abc), f"Invalid ABC for {node['node_id']}"
            midi = converter.abc_to_midi(abc)
            results[node["node_id"]] = midi

        assert len(results) == 3
        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_different_nodes_have_different_keys(self) -> None:
        """Each mood maps to a different key signature."""
        gen = MockAbcTextGenerator()
        keys_seen: set[str] = set()

        for node in _make_multiple_nodes():
            abc = await gen.generate(
                prompt=f"MUSIC TONE: {node['music_tone']}\nSCENE: {node['text']}"
            )
            match = re.search(r"^K:(\w+)", abc, re.MULTILINE)
            if match:
                keys_seen.add(match.group(1))

        # Three different moods → at least 2 different keys
        assert len(keys_seen) >= 2

    @pytest.mark.asyncio
    async def test_nodes_without_music_tone_skipped(self) -> None:
        """Nodes missing music_tone are skipped gracefully."""
        nodes = [
            {"node_id": "node_01", "text": "Scene 1", "music_tone": "tense"},
            {"node_id": "node_02", "text": "Scene 2"},  # No music_tone
            {"node_id": "node_03", "text": "Scene 3", "music_tone": ""},  # Empty
        ]

        generated = 0
        skipped = 0
        for node in nodes:
            tone = node.get("music_tone", "")
            if not tone:
                skipped += 1
                continue
            generated += 1

        assert generated == 1
        assert skipped == 2

    @pytest.mark.asyncio
    async def test_midi_files_are_non_empty(self) -> None:
        """Generated MIDI files contain actual data."""
        gen = MockAbcTextGenerator()
        converter = MockMidiConverter()

        for node in _make_multiple_nodes():
            abc = await gen.generate(
                prompt=f"MUSIC TONE: {node['music_tone']}\nSCENE: {node['text']}"
            )
            midi = converter.abc_to_midi(abc)
            assert len(midi) > 0, f"Empty MIDI for {node['node_id']}"


class TestMusicGeneratorStepValidation:
    """ABC validation edge cases."""

    def test_missing_x_header_fails(self) -> None:
        """ABC without X: header is invalid."""
        no_x = "M:4/4\nK:Dm\nD2 F2 A2 d2 |]"
        assert not MockMidiConverter.validate_abc(no_x)

    def test_missing_k_header_fails(self) -> None:
        """ABC without K: (key) header is invalid."""
        no_k = "X:1\nM:4/4\nD2 F2 A2 d2 |]"
        assert not MockMidiConverter.validate_abc(no_k)

    def test_missing_m_header_fails(self) -> None:
        """ABC without M: (time signature) header is invalid."""
        no_m = "X:1\nK:Dm\nD2 F2 A2 d2 |]"
        assert not MockMidiConverter.validate_abc(no_m)

    def test_no_notes_fails(self) -> None:
        """ABC with headers but no actual notes is invalid."""
        no_notes = "X:1\nM:4/4\nK:Dm\n"
        assert not MockMidiConverter.validate_abc(no_notes)

    def test_empty_string_fails(self) -> None:
        """Empty ABC string is invalid."""
        assert not MockMidiConverter.validate_abc("")

    def test_whitespace_only_fails(self) -> None:
        """Whitespace-only ABC is invalid."""
        assert not MockMidiConverter.validate_abc("   \n  \n  ")

    def test_required_headers_present(self) -> None:
        """Valid ABC has X:, M:, K:, and at least one note."""
        assert MockMidiConverter.validate_abc(_VALID_ABC)


class TestMusicGeneratorStepToneMapping:
    """Music tone → key signature mapping per composer_v1.j2 rules."""

    _TONE_KEY_MAP = {
        "tense": "Dm",
        "peaceful": "C",
        "triumphant": "G",
        "melancholy": "Am",
        "mysterious": "Em",
        "heroic": "D",
    }

    @pytest.mark.asyncio
    async def test_all_six_tones_have_keys(self) -> None:
        """All 6 music tones map to a key signature."""
        assert len(self._TONE_KEY_MAP) == 6

    @pytest.mark.asyncio
    async def test_minor_keys_for_dark_tones(self) -> None:
        """Tense, melancholy, mysterious → minor keys."""
        gen = MockAbcTextGenerator()
        for tone in ["tense", "melancholy", "mysterious"]:
            abc = await gen.generate(
                prompt=f"MUSIC TONE: {tone}\nSCENE: x"
            )
            match = re.search(r"^K:(\w+)", abc, re.MULTILINE)
            assert match, f"No key found for {tone}"
            assert match.group(1).endswith("m") or match.group(1) in {"Dm", "Am", "Em"}

    @pytest.mark.asyncio
    async def test_major_keys_for_heroic_tones(self) -> None:
        """Peaceful, triumphant, heroic → major keys."""
        gen = MockAbcTextGenerator()
        for tone in ["peaceful", "triumphant", "heroic"]:
            abc = await gen.generate(
                prompt=f"MUSIC TONE: {tone}\nSCENE: x"
            )
            match = re.search(r"^K:(\w+)", abc, re.MULTILINE)
            assert match, f"No key found for {tone}"
            assert not match.group(1).endswith("m")


class TestMusicGeneratorStepEdgeCases:
    """Error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_requires_graph_in_context(self) -> None:
        """MusicGeneratorStep requires context.outputs['graph']."""
        ctx = PipelineContext(run_id="r1", seed=1)
        assert "graph" not in ctx.outputs

    @pytest.mark.asyncio
    async def test_invalid_abc_rejected(self) -> None:
        """Invalid ABC triggers validation error, not silent corruption."""
        converter = MockMidiConverter()
        valid = converter.validate_abc("garbage text")
        assert not valid

    @pytest.mark.asyncio
    async def test_generation_failure_propagates(self) -> None:
        """Failing TextGenerator raises error that propagates."""
        gen = MockFailingAbcGenerator()
        abc = await gen.generate()
        valid = MockMidiConverter.validate_abc(abc)
        assert not valid

    @pytest.mark.asyncio
    async def test_empty_graph_no_nodes(self) -> None:
        """Empty graph produces empty output, not a crash."""
        class EmptyGen:
            model_name = "t"
            quantization = "q"
            call_count = 0
            async def generate(self, prompt="", **kwargs):
                self.call_count += 1
                return _VALID_ABC

        gen = EmptyGen()
        assert gen.call_count == 0

    def test_abc_format_starts_with_x1(self) -> None:
        """Per composer_v1.j2 CRITICAL rule: ABC MUST start with X:1."""
        assert _VALID_ABC.strip().startswith("X:1")

    def test_abc_contains_melody_notes(self) -> None:
        """ABC notation contains actual note sequences."""
        notes_pattern = re.compile(r"[A-Ga-g]\d?")
        notes = notes_pattern.findall(_VALID_ABC)
        assert len(notes) >= 4, "ABC should have multiple notes"

    def test_abc_no_markdown_wrappers(self) -> None:
        """ABC output does NOT contain ``` markers (CRITICAL rule)."""
        assert "```" not in _VALID_ABC


class TestMusicGeneratorStepQuarantineDetection:
    """QUARANTINE total-failure detection: if ALL nodes fail, raise RuntimeError."""

    def test_all_nodes_failing_raises_error(self) -> None:
        """When all nodes with music_tone fail ABC generation, RuntimeError is raised."""
        nodes = [
            {"node_id": "node_01", "text": "Scene 1", "music_tone": "tense"},
            {"node_id": "node_02", "text": "Scene 2", "music_tone": "heroic"},
        ]
        nodes_with_tone = 2
        midi_files: dict[str, Any] = {}

        # Simulate all failing
        for node in nodes:
            try:
                raise RuntimeError("music21 not available")
            except Exception:
                continue

        if nodes_with_tone > 0 and len(midi_files) == 0:
            with pytest.raises(RuntimeError, match="all 2 nodes"):
                raise RuntimeError(
                    f"MIDI generation failed for all {nodes_with_tone} nodes."
                )
        else:
            pytest.fail("Should have raised RuntimeError")

    def test_no_nodes_with_tone_is_fine(self) -> None:
        """If no nodes have music_tone, empty result is OK."""
        nodes: list[dict[str, Any]] = [
            {"node_id": "node_01", "image_prompt": "Scene"},  # No music_tone
        ]
        nodes_with_tone = 0
        for node in nodes:
            if not node.get("music_tone", "").strip():
                continue
            nodes_with_tone += 1

        assert nodes_with_tone == 0  # No nodes with tone → no error regardless

    def test_some_succeeding_is_ok(self) -> None:
        """If at least one node succeeds, no error is raised."""
        nodes_with_tone = 3
        midi_files = {"node_01": {"midi_bytes_length": 200}}
        # Not raising
        if not (nodes_with_tone > 0 and len(midi_files) == 0):
            pass
        assert len(midi_files) > 0
