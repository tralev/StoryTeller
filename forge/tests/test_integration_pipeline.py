"""Integration test: Bible → Story → Graph → Image → Music → Index → Package.

Tests the full App B pipeline end-to-end with mock generators.
Verifies that all steps chain correctly — context flows from one step to the next,
artifact IDs are generated, and the final .story package is valid.
"""

from __future__ import annotations

import json
import tempfile
from typing import Any
from pathlib import Path

import pytest

from src.job_queue import PipelineContext
from src.models.base import PipelineError, StepOutput


# ── Mock generators ──────────────────────────────────────────────────────────


class MockTextGenerator:
    """Returns valid but minimal JSON matching the requested schema."""

    model_name: str = "mock-7b"
    quantization: str = "Q4"
    call_count: int = 0
    last_prompt: str = ""

    async def generate(
        self,
        prompt: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        self.call_count += 1
        self.last_prompt = prompt

        # Detect what's being generated from the prompt content
        if '"world_name"' in prompt:
            return self._mock_bible(seed or 0)
        elif '"art_style"' in prompt or "character_design" in prompt:
            return self._mock_style_bible()
        elif "decision_points" in prompt:
            return self._mock_decision_points()
        elif '"nodes"' in prompt and '"node_id"' in prompt:
            return self._mock_graph_skeleton()
        elif "CRITICAL CONSTRAINTS" in prompt and "10 words or fewer" in prompt:
            return self._mock_node_text()
        elif "Write Chapter " in prompt or "Generate a 3-part story outline" in prompt:
            return self._mock_chapter(seed or 0)
        elif "X:1" in prompt or "MUSIC TONE" in prompt:
            return self._mock_abc(seed or 0)
        return {}

    @staticmethod
    def _mock_bible(seed: int) -> dict[str, Any]:
        return {
            "world_name": "Test World",
            "narrative_rules": {
                "tone": "dark_fantasy",
                "forbidden": [],
                "required_themes": ["sacrifice"],
                "mortality": "moderate",
                "knowledge_level": "aware",
            },
            "entities": {
                "characters": [
                    {
                        "id": "char_01",
                        "name": "Kael",
                        "aliases": ["The Wanderer"],
                        "description": "A weary traveler.",
                        "role": "protagonist",
                        "archetype": "hero",
                        "motivation": "Redemption",
                        "flaw": "Pride",
                        "strength": "Courage",
                        "relationships": [{"target": "char_02", "type": "ally"}],
                        "status": "alive",
                        "nodes": ["node_01"],
                    },
                    {
                        "id": "char_02",
                        "name": "Lyra",
                        "aliases": ["The Guide"],
                        "description": "A mysterious guide.",
                        "role": "supporting",
                        "archetype": "mentor",
                        "motivation": "Duty",
                        "flaw": "Secrecy",
                        "strength": "Wisdom",
                        "relationships": [{"target": "char_01", "type": "ally"}],
                        "status": "alive",
                        "nodes": ["node_01"],
                    },
                ],
                "locations": [
                    {
                        "id": "loc_01",
                        "name": "The Salt Wastes",
                        "aliases": ["The Wastes"],
                        "description": "Endless white salt flats.",
                        "type": "wilderness",
                        "mood": "desolate",
                        "danger": "moderate",
                        "connected_to": ["loc_02"],
                        "nodes": ["node_01"],
                    },
                    {
                        "id": "loc_02",
                        "name": "The Cathedral",
                        "aliases": ["Salt Cathedral"],
                        "description": "A ruined salt cathedral.",
                        "type": "dungeon",
                        "mood": "holy",
                        "danger": "high",
                        "connected_to": ["loc_01"],
                        "nodes": ["node_02"],
                    },
                ],
                "factions": [
                    {
                        "id": "fac_01",
                        "name": "The Salt Priests",
                        "aliases": ["Priests"],
                        "description": "Guardians of salt magic.",
                        "type": "religious",
                        "members": ["char_02"],
                        "nodes": ["node_02"],
                    },
                ],
                "creatures": [
                    {
                        "id": "cre_01",
                        "name": "Salt Wraith",
                        "aliases": ["Wraith"],
                        "description": "Translucent salt spirits.",
                        "danger": "high",
                        "nodes": ["node_02"],
                    },
                ],
                "artifacts": [
                    {
                        "id": "art_01",
                        "name": "God-Heart",
                        "aliases": ["The Heart"],
                        "description": "Crystallized divine essence.",
                        "nodes": ["node_03"],
                    },
                ],
                "events": [],
            },
            "systems": {
                "magic": {
                    "source": "Salt",
                    "rules": ["Salt draws life", "Fades at dawn"],
                    "costs": ["Vitality"],
                    "limitations": "None at night",
                },
                "politics": {"power_structure": "Theocracy", "conflicts": []},
                "religion": {"gods": ["The Silent One"], "afterlife": "Salt Dream"},
            },
        }

    @staticmethod
    def _mock_style_bible() -> dict[str, Any]:
        return {
            "art_style": {
                "palette": "cold blue, white, grey",
                "lighting": "moonlight, low-key",
                "composition": "off-center, depth",
                "linework": "ink hatching, rough edges",
                "mood": "melancholy, ancient",
                "forbidden": [
                    "modern technology", "neon colors", "photorealism",
                    "3d render", "anime style", "smiling figures",
                    "text", "UI elements",
                ],
            },
            "character_design": {
                "char_01": "Weathered wanderer in salt-stained leather.",
                "char_02": "Masked priest in bleached robes, tall and gaunt.",
            },
            "location_palettes": {
                "loc_01": "Endless white salt flats, pale blue sky.",
                "loc_02": "Glowing white salt cathedral, amber candlelight.",
            },
        }

    @staticmethod
    def _mock_chapter(seed: int) -> dict[str, Any]:
        return {
            "number": (seed % 3) + 1,
            "title": f"Chapter {(seed % 3) + 1}",
            "summary": "A chapter summary.",
            "scenes": [
                {
                    "scene_id": "scene_01_01",
                    "text": "The wind howled across the salt wastes. "
                           "Kael pulled his cloak tighter and pressed on. "
                           "Lyra walked beside him, silent as always. "
                           "The horizon stretched endlessly white.",
                    "characters_present": ["char_01", "char_02"],
                    "location": "loc_01",
                    "entities_referenced": [],
                    "word_count": 45,
                }
            ],
        }

    @staticmethod
    def _mock_decision_points() -> dict[str, Any]:
        return {
            "decision_points": [
                {
                    "dp_id": "dp_01",
                    "chapter": 1,
                    "scene_ref": "scene_01_01",
                    "description": "Choose direction through the wastes.",
                    "possible_choices": ["North", "South"],
                    "stakes": "Survival",
                    "characters_involved": ["char_01", "char_02"],
                    "location": "loc_01",
                },
                {
                    "dp_id": "dp_02",
                    "chapter": 2,
                    "scene_ref": "scene_02_01",
                    "description": "Enter or bypass the cathedral.",
                    "possible_choices": ["Enter", "Bypass"],
                    "stakes": "Discovery",
                    "characters_involved": ["char_01"],
                    "location": "loc_02",
                },
            ],
        }

    @staticmethod
    def _mock_graph_skeleton() -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "node_id": "node_01",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "description": "The wastes stretch before you.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_01",
                    "present_creatures": [],
                    "mood": "desolate",
                    "choices": [
                        {
                            "choice_id": "ch_01_a",
                            "choice_text": "Head north toward the spire.",
                            "target_node": "node_02",
                            "sets_flags": ["chose_north"],
                        },
                        {
                            "choice_id": "ch_01_b",
                            "choice_text": "Go south into the basin.",
                            "target_node": "node_03",
                            "sets_flags": ["chose_south"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_02",
                    "chapter": 2,
                    "scene_type": "combat",
                    "description": "A wraith blocks your path.",
                    "present_characters": ["char_01"],
                    "present_location": "loc_02",
                    "present_creatures": ["cre_01"],
                    "mood": "tense",
                    "choices": [
                        {
                            "choice_id": "ch_02_a",
                            "choice_text": "Fight the wraith.",
                            "target_node": "node_04",
                            "sets_flags": ["fought_wraith"],
                            "requires_flags": ["chose_north"],
                        },
                        {
                            "choice_id": "ch_02_b",
                            "choice_text": "Sneak past.",
                            "target_node": "node_05",
                            "requires_flags": ["chose_north"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_03",
                    "chapter": 2,
                    "scene_type": "exploration",
                    "description": "The basin is quiet.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_01",
                    "present_creatures": [],
                    "mood": "peaceful",
                    "choices": [
                        {
                            "choice_id": "ch_03_a",
                            "choice_text": "Rest here.",
                            "target_node": "node_06",
                            "requires_flags": ["chose_south"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_04",
                    "chapter": 3,
                    "scene_type": "combat",
                    "description": "The wraith shatters.",
                    "present_characters": ["char_01"],
                    "present_location": "loc_02",
                    "present_creatures": [],
                    "mood": "triumphant",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "heroic", "ending_title": "Victory"},
                },
                {
                    "node_id": "node_05",
                    "chapter": 3,
                    "scene_type": "exploration",
                    "description": "You slip past unnoticed.",
                    "present_characters": ["char_01"],
                    "present_location": "loc_02",
                    "present_creatures": [],
                    "mood": "tense",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "dark", "ending_title": "Silent Passage"},
                },
                {
                    "node_id": "node_06",
                    "chapter": 2,
                    "scene_type": "exploration",
                    "description": "A quiet camp.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_01",
                    "present_creatures": [],
                    "mood": "peaceful",
                    "choices": [
                        {
                            "choice_id": "ch_06_a",
                            "choice_text": "Continue the journey.",
                            "target_node": "node_07",
                            "requires_flags": ["chose_south"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_07",
                    "chapter": 3,
                    "scene_type": "exploration",
                    "description": "The God-Heart awaits.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_02",
                    "present_creatures": [],
                    "mood": "mysterious",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "mythic", "ending_title": "The Heart"},
                },
                {
                    "node_id": "node_08",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "description": "Finding the trail.",
                    "present_characters": ["char_01"],
                    "present_location": "loc_01",
                    "present_creatures": [],
                    "mood": "desolate",
                    "choices": [
                        {"choice_id": "ch_08_a", "choice_text": "Follow tracks.", "target_node": "node_09"},
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_09",
                    "chapter": 2,
                    "scene_type": "combat",
                    "description": "Ambush.",
                    "present_characters": ["char_01"],
                    "present_location": "loc_02",
                    "present_creatures": ["cre_01"],
                    "mood": "tense",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "dark", "ending_title": "Ambushed"},
                },
                {
                    "node_id": "node_10",
                    "chapter": 3,
                    "scene_type": "ending",
                    "description": "Final choice.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_02",
                    "present_creatures": [],
                    "mood": "triumphant",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "heroic", "ending_title": "Freedom"},
                },
            ],
        }

    @staticmethod
    def _mock_node_text() -> dict[str, Any]:
        return {
            "text": "The wind howled.\nYou grip your cloak.\n"
                   "A path lies ahead.\nNorth or south?\n"
                   "Lyra watches silently.\nThe choice is yours.\n"
                   "What will you do?",
            "choices": [
                {"choice_id": "ch_01_a", "choice_text": "North", "target_node": "node_02",
                 "text": "Head north toward the spire.", "sets_flags": ["chose_north"]},
                {"choice_id": "ch_01_b", "choice_text": "South", "target_node": "node_03",
                 "text": "Go south into the basin.", "sets_flags": ["chose_south"]},
            ],
            "mood": "desolate",
            "image_prompt": "A lone figure at the edge of endless white salt flats",
            "music_tone": "melancholy",
        }

    @staticmethod
    def _mock_abc(seed: int) -> str:
        keys = ["Dm", "Am", "Em", "G", "C", "D"]
        return (
            "X:1\n"
            "T:Scene\n"
            "M:4/4\n"
            "L:1/8\n"
            f"K:{keys[seed % len(keys)]}\n"
            "D2 F2 A2 d2 | c2 A2 F2 D2 | E2 G2 c2 e2 | d8 |]\n"
        )


class MockImageGenerator:
    """Returns deterministic PNG bytes."""

    provider: str = "mock-sd"
    model_name: str = "mock"
    quantization: str = "Q4"
    call_count: int = 0

    async def generate(
        self, prompt: str = "", negative_prompt: str = "",
        size: tuple[int, int] = (512, 512), seed: int | None = None, steps: int = 20,
    ) -> bytes:
        self.call_count += 1
        return b"\x89PNG\r\n\x1a\n" + int(seed or 0).to_bytes(4, "big") * 64

    async def generate_thumbnail(
        self, image_bytes: bytes = b"", size: tuple[int, int] = (128, 128),
    ) -> bytes:
        return b"\x89PNG\r\n" + image_bytes[:64]


class MockMusicGenerator:
    """Validates ABC and converts to MIDI bytes."""

    provider: str = "abc-notation"
    call_count: int = 0

    async def generate(self, scene_text: str = "", mood: str = "", seed: int | None = None) -> str:
        return MockTextGenerator._mock_abc(seed or 0)

    @staticmethod
    def abc_to_midi(abc_notation: str) -> bytes:
        return b"MThd" + abc_notation.encode()[:100]

    @staticmethod
    def validate_abc(abc_notation: str) -> bool:
        return abc_notation.strip().startswith("X:1") and "K:" in abc_notation and "M:" in abc_notation


# ── Integration tests ────────────────────────────────────────────────────────


class TestPipelineIntegration:
    """Full pipeline: Bible → Story → Graph → Image → Music → Index → Package."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_package(self) -> None:
        """End-to-end: all steps chain together and produce a .story ZIP."""
        from src.models.art_director import ArtDirector
        from src.models.game_designer import GameDesigner
        from src.models.image_generator_step import ImageGeneratorStep
        from src.models.music_generator_step import MusicGeneratorStep
        from src.models.story_writer import StoryWriter
        from src.models.world_builder import WorldBuilder
        from src.storage.indexer import GmIndexer
        from src.storage.packager import Packager

        with tempfile.TemporaryDirectory() as tmpdir:
            text_gen = MockTextGenerator()
            img_gen = MockImageGenerator()
            mus_gen = MockMusicGenerator()

            ctx = PipelineContext(run_id="test_run", seed=42)
            ctx.state["tone"] = "dark_fantasy"
            ctx.state["title"] = "Salt and Silence"
            ctx.state["temperature"] = 0.7
            ctx.state["start_time"] = __import__("time").time()

            # Phase 1: World Bible
            wb = WorldBuilder(text_gen, config=None)
            output = await wb.run(ctx)
            ctx.outputs["bible"] = output.data
            assert output.artifact_id.startswith("world_")
            assert "Kael" in str(output.data)

            # Phase 2: Style Bible
            ad = ArtDirector(text_gen, config=None)
            output = await ad.run(ctx)
            ctx.outputs["style_bible"] = output.data
            assert output.artifact_id.startswith("style_")
            assert "art_style" in output.data

            # Phase 3: Story
            sw = StoryWriter(text_gen, config=None)
            output = await sw.run(ctx)
            ctx.outputs["story"] = output.data
            assert output.artifact_id.startswith("story_")
            assert len(output.data["chapters"]) == 3

            # Phase 4: CYOA Graph
            gd = GameDesigner(text_gen, config=None)
            output = await gd.run(ctx)
            ctx.outputs["graph"] = output.data
            assert output.artifact_id.startswith("graph_")
            assert len(output.data["nodes"]) >= 10

            # Phase 5a: Images
            istep = ImageGeneratorStep(img_gen, config=None)
            output = await istep.run(ctx)
            ctx.outputs["images"] = output.data
            assert output.artifact_id.startswith("img_")
            assert output.data["image_count"] >= 1

            # Phase 5b: Music
            mstep = MusicGeneratorStep(text_gen, mus_gen, config=None)
            output = await mstep.run(ctx)
            ctx.outputs["midi"] = output.data
            assert output.artifact_id.startswith("mid_")
            assert output.data["midi_count"] >= 1

            # Phase 6: GM Index
            idx = GmIndexer()
            output = await idx.run(ctx)
            ctx.outputs["gm_index"] = output.data
            assert output.artifact_id.startswith("gmindex_")
            assert "keywords" in output.data
            assert "entity_cache" in output.data

            # Phase 7: Package
            ctx.outputs["manifest"] = {
                "schema_version": 1,
                "generator_version": "0.1.0",
                "pipeline_version": 1,
                "created_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
                "model_versions": {"text_generator": "mock-7b-Q4"},
                "seed": 42,
                "title": "Salt and Silence",
                "artifact_id": "package_test1234",
                "stats": {},
            }

            pkg = Packager(output_dir=tmpdir)
            output = await pkg.run(ctx)
            assert output.artifact_id.startswith("package_")

            # Verify the .story ZIP exists and contains expected files
            package_path = Path(output.data["package_path"])
            assert package_path.exists()
            assert package_path.suffix == ".story"

            import zipfile
            with zipfile.ZipFile(package_path) as zf:
                names = zf.namelist()
                assert "manifest.json" in names
                assert "content/bible.json" in names
                assert "content/story.json" in names
                assert "content/graph.json" in names
                assert "content/gm_index.json" in names
                assert "content/style_bible.json" in names
                assert "save/.gitkeep" in names

            # Verify the ZIP is valid
            assert package_path.stat().st_size > 0

    @pytest.mark.integration
    def test_pipeline_context_flows_between_steps(self) -> None:
        """Context.outputs accumulates results as steps complete."""
        ctx = PipelineContext(run_id="flow_test", seed=1)

        # Simulate step outputs being stored in context
        ctx.outputs["bible"] = {"world_name": "Test"}
        ctx.outputs["style_bible"] = {"art_style": {}}
        ctx.outputs["story"] = {"chapters": []}
        ctx.outputs["graph"] = {"nodes": []}
        ctx.outputs["images"] = {"images": {}}
        ctx.outputs["midi"] = {"midi": {}}
        ctx.outputs["gm_index"] = {"keywords": {}}

        # All outputs should be accessible
        assert ctx.outputs.get("bible") is not None
        assert ctx.outputs.get("graph") is not None
        assert ctx.outputs.get("gm_index") is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pipeline_is_deterministic_with_same_seed(self) -> None:
        """Same seed twice → identical outputs (with mocks)."""
        from src.models.world_builder import WorldBuilder

        ctx1 = PipelineContext(run_id="run1", seed=42)
        ctx1.state["tone"] = "dark_fantasy"
        ctx1.state["title"] = "Test"

        ctx2 = PipelineContext(run_id="run2", seed=42)
        ctx2.state["tone"] = "dark_fantasy"
        ctx2.state["title"] = "Test"

        wb1 = WorldBuilder(MockTextGenerator(), config=None)
        wb2 = WorldBuilder(MockTextGenerator(), config=None)

        out1 = await wb1.run(ctx1)
        out2 = await wb2.run(ctx2)

        # Same seed → same artifact_id (deterministic content hash)
        assert out1.artifact_id == out2.artifact_id
        assert json.dumps(out1.data, sort_keys=True) == json.dumps(out2.data, sort_keys=True)


class TestCliEntryPoint:
    """CLI entry point is importable and wired correctly."""

    def test_main_is_importable(self) -> None:
        """src.cli.main exists and is callable."""
        from src.cli import main
        assert callable(main)

    def test_stub_config_is_valid(self) -> None:
        """_stub_config returns a valid AppConfig."""
        from src.cli import _stub_config
        config = _stub_config()
        assert config.text_generator.model == "qwen2.5-7b"
        assert config.image_generator.model == "sdxl-turbo"
        assert config.music_generator.model == "via-text"
        assert config.limits.max_ram_mb == 10240


class TestPipelineErrorRecovery:
    """QUARANTINE and ABORT behavior in the full pipeline context."""

    @pytest.mark.asyncio
    async def test_world_builder_aborts_on_failure(self) -> None:
        """WorldBuilder with ABORT policy raises PipelineError on failure."""
        from src.models.world_builder import WorldBuilder
        from src.models.base import PipelineError

        class FailingGenerator:
            model_name = "fail"
            quantization = "x"
            async def generate(self, prompt="", **kwargs):
                raise RuntimeError("Model crashed")

        ctx = PipelineContext(run_id="abort", seed=1)
        ctx.state["tone"] = "test"
        ctx.state["title"] = "test"

        from src.job_queue import FailurePolicy
        wb = WorldBuilder(FailingGenerator(), config=None, failure_policy=FailurePolicy.ABORT)
        with pytest.raises(PipelineError, match="world_builder"):
            await wb.run(ctx)

    @pytest.mark.asyncio
    async def test_story_writer_requires_bible(self) -> None:
        """StoryWriter raises PipelineError if bible not in context."""
        from src.models.story_writer import StoryWriter

        ctx = PipelineContext(run_id="no_bible", seed=1)
        sw = StoryWriter(MockTextGenerator(), config=None)

        with pytest.raises(PipelineError, match="story_writer"):
            await sw.run(ctx)

    @pytest.mark.asyncio
    async def test_game_designer_requires_bible_and_story(self) -> None:
        """GameDesigner raises PipelineError if bible or story not in context."""
        from src.models.game_designer import GameDesigner

        ctx = PipelineContext(run_id="no_bible", seed=1)
        gd = GameDesigner(MockTextGenerator(), config=None)

        with pytest.raises(PipelineError, match="game_designer"):
            await gd.run(ctx)

        ctx.outputs["bible"] = {"entities": {}}
        with pytest.raises(PipelineError, match="game_designer"):
            await gd.run(ctx)

    @pytest.mark.asyncio
    async def test_image_step_requires_graph_and_style(self) -> None:
        """ImageGeneratorStep raises PipelineError if graph or style_bible missing."""
        from src.models.image_generator_step import ImageGeneratorStep

        ctx = PipelineContext(run_id="no_graph", seed=1)
        step = ImageGeneratorStep(MockImageGenerator(), config=None)

        with pytest.raises(PipelineError, match="image_generator"):
            await step.run(ctx)

        ctx.outputs["graph"] = {"nodes": []}
        with pytest.raises(PipelineError, match="image_generator"):
            await step.run(ctx)
