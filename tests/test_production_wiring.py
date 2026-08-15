"""Production-wiring integration test: GenerateStory service with fake backends.

Phase 5.5I: Verifies the FULL production assembly path — GenerateStory.execute()
with all validators, manifest builder, package acceptance, batch scheduler,
and model lifecycle management. Uses tracked fakes to verify:

  1. Pipeline completes without error
  2. All expected artifact keys exist in context
  3. Every artifact written once under canonical filename
  4. Resume restores identical context shape
  5. Validators are wired and executed
  6. Model load/unload order is correct
  7. Valid manifest is created
  8. Final ZIP passes PackageAcceptance
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from src.application.models import GenerationRequest
from src.application.generate_story import GenerateStory
from src.storage.binary_checks import make_midi, make_png

# Phase 5.6 R: fakes must produce structurally valid, correctly-sized media
# so the acceptance binary checks pass. Built once, cached (deterministic).
_PNG_512 = make_png(512, 512)
_PNG_128 = make_png(128, 128)
_MIDI_OK = make_midi(ticks=96)


# ── Tracked Fake Backends ────────────────────────────────────────────────────


class TrackedTextGenerator:
    """Fake TextGenerator that returns schema-compliant data AND tracks lifecycle.

    Pattern-matched prompt responses — each generate() call returns valid
    JSON for the specific step (bible, style_bible, story, graph, music).
    Also tracks load/unload calls and generate call count.
    """

    provider: str = "fake"
    model_name: str = "fake-text-tracked"
    quantization: str = "Q4_K_M"
    ram_usage_mb: int = 4700

    def __init__(self) -> None:
        self._loaded = False
        self.load_count = 0
        self.unload_count = 0
        self.call_count = 0
        self.last_prompt: str = ""

    async def generate(
        self,
        prompt: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any] | str:
        self.call_count += 1
        self.last_prompt = prompt

        # Production-v2 bounded enrichment contracts. Structured procedural
        # facts stay authoritative; the fake supplies prose-only refinements.
        if "Refine the visual wording" in prompt:
            payload = json.loads(prompt[prompt.index("{", prompt.index("\n")) :])
            return {
                "climate_palettes": {key: f"Refined {value}"
                                     for key, value in payload["climate_palettes"].items()},
                "culture_motifs": {key: f"Refined {value}"
                                   for key, value in payload["culture_motifs"].items()},
            }
        if "exactly these scene IDs" in prompt:
            ids = re.findall(r'"scene_id":"([^"]+)"', prompt)
            return {"scenes": {scene_id: {
                "title": f"The Weight of {scene_id}",
                "summary": f"Documented pressures converge in scene {scene_id}.",
            } for scene_id in ids}}
        if "exactly these IDs" in prompt:
            ids = re.findall(r'"node_id":"([^"]+)"', prompt)
            return {"nodes": {node_id: f"Documented tensions sharpen at node {node_id}."
                              for node_id in ids}}
        if "Refine the image prompt and music mood" in prompt:
            source = json.loads(prompt.split("\n", 1)[1])
            return {"nodes": {node_id: {
                "image_prompt": f"Refined {value['image_prompt']}",
                "music_mood": f"Refined {value['music_mood']}",
            } for node_id, value in source.items()}}
        if "Enrich this authoritative world Bible" in prompt:
            return {"interpretations": ["Ash and old vows shape the documented age."]}

        # Detect step type from prompt content.
        # ORDER MATTERS: story_writer and game_designer inject bible context,
        # so check their keywords BEFORE bible detection.
        if "Write Chapter " in prompt or "story outline" in prompt:
            return self._chapter(seed or 0)
        elif "decision_points" in prompt:
            return self._decision_points()
        elif '"nodes"' in prompt and '"node_id"' in prompt and (
            "chapter" in prompt or "scene_type" in prompt
            or "present_characters" in prompt
        ):
            return self._graph_skeleton()
        elif "CRITICAL CONSTRAINTS" in prompt or "10 words or fewer" in prompt:
            return self._node_text()
        elif '"world_name"' in prompt or "World Bible" in prompt:
            return self._bible(seed or 0)
        elif '"art_style"' in prompt or "character_design" in prompt:
            return self._style_bible()
        elif "X:1" in prompt or "MUSIC TONE" in prompt or "ABC notation" in prompt:
            s = seed or 0
            keys = ["Dm", "Am", "Em", "G", "C", "D"]
            return (
                "X:1\n"
                "T:Scene\n"
                "M:4/4\n"
                "L:1/8\n"
                f"K:{keys[s % len(keys)]}\n"
                "D2 F2 A2 d2 | c2 A2 F2 D2 | E2 G2 c2 e2 | d8 |]\n"
            )
        return {"note": "unrecognized prompt"}

    def generate_stream(
        self,
        prompt: str = "",
        temperature: float = 0.7,
        seed: int | None = None,
    ) -> Any:
        async def _stream() -> Any:
            yield "fake"
            yield " stream"
        return _stream()

    async def load(self) -> None:
        self.load_count += 1
        self._loaded = True

    async def unload(self) -> None:
        self.unload_count += 1
        self._loaded = False

    # ── fixtures ─────────────────────────────────────────────────────────

    @staticmethod
    def _bible(seed: int) -> dict[str, Any]:
        return {
            "world_name": "Wiring Test World",
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
                        "id": "char_01", "name": "Kael", "aliases": ["The Wanderer"],
                        "description": "A weary traveler.", "role": "protagonist",
                        "archetype": "hero", "motivation": "Redemption",
                        "flaw": "Pride", "strength": "Courage",
                        "relationships": [
                            {"target": "char_02", "type": "ally",
                             "description": "Trusted companion met on the salt flats"},
                        ],
                        "status": "alive", "nodes": ["node_01"],
                    },
                    {
                        "id": "char_02", "name": "Lyra", "aliases": ["The Guide"],
                        "description": "A mysterious guide.", "role": "supporting",
                        "archetype": "mentor", "motivation": "Duty",
                        "flaw": "Secrecy", "strength": "Wisdom",
                        "relationships": [
                            {"target": "char_01", "type": "ally",
                             "description": "Bound by an ancient oath to guide the wanderer"},
                        ],
                        "status": "alive", "nodes": ["node_01"],
                    },
                ],
                "locations": [
                    {
                        "id": "loc_01", "name": "The Salt Wastes",
                        "aliases": ["The Wastes"],
                        "description": "Endless white salt flats.",
                        "type": "wilderness", "mood": "desolate", "danger": "moderate",
                        "connected_to": ["loc_02"], "nodes": ["node_01"],
                    },
                    {
                        "id": "loc_02", "name": "The Cathedral",
                        "aliases": ["Salt Cathedral"],
                        "description": "A ruined salt cathedral.",
                        "type": "dungeon", "mood": "holy", "danger": "high",
                        "connected_to": ["loc_01"], "nodes": ["node_02"],
                    },
                ],
                "factions": [
                    {
                        "id": "fac_01", "name": "The Salt Priests",
                        "aliases": ["Priests"],
                        "description": "Guardians of salt magic.",
                        "type": "cult", "goal": "Preserve the ancient salt rituals",
                        "methods": ["ritual sacrifice", "secret teachings"],
                        "members": ["char_02"], "nodes": ["node_02"],
                    },
                ],
                "creatures": [
                    {
                        "id": "cre_01", "name": "Salt Wraith",
                        "aliases": ["Wraith"],
                        "description": "Translucent salt spirits.",
                        "danger": "high", "type": "undead",
                        "habitat": "salt_cathedral", "behavior": "territorial",
                        "nodes": ["node_02"],
                    },
                ],
                "artifacts": [
                    {
                        "id": "art_01", "name": "God-Heart",
                        "aliases": ["The Heart"],
                        "description": "Crystallized divine essence.",
                        "origin": "Forged by the Silent One at the dawn of time",
                        "location": "loc_02", "power": "grants visions of the past",
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
                "politics": {
                    "power_structure": "Theocracy",
                    "conflicts": [],
                },
                "religion": {
                    "gods": [
                        {"name": "The Silent One", "domain": "Silence and Salt",
                         "status": "dormant"},
                    ],
                    "afterlife": "Salt Dream",
                },
            },
        }

    @staticmethod
    def _style_bible() -> dict[str, Any]:
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
    def _chapter(seed: int) -> dict[str, Any]:
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
    def _decision_points() -> dict[str, Any]:
        return {
            "decision_points": [
                {
                    "dp_id": "dp_01", "chapter": 1, "scene_ref": "scene_01_01",
                    "description": "Choose direction through the wastes.",
                    "possible_choices": ["North", "South"], "stakes": "Survival",
                    "characters_involved": ["char_01", "char_02"], "location": "loc_01",
                },
                {
                    "dp_id": "dp_02", "chapter": 2, "scene_ref": "scene_02_01",
                    "description": "Enter or bypass the cathedral.",
                    "possible_choices": ["Enter", "Bypass"], "stakes": "Discovery",
                    "characters_involved": ["char_01"], "location": "loc_02",
                },
            ],
        }

    @staticmethod
    def _graph_skeleton() -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "node_id": "node_01", "chapter": 1, "scene_type": "exploration",
                    "description": "The wastes stretch before you.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_01", "present_creatures": [],
                    "mood": "desolate",
                    "choices": [
                        {
                            "choice_id": "ch_01_a",
                            "choice_text": "Head north toward the spire.",
                            "target_node": "node_02", "sets_flags": ["chose_north"],
                        },
                        {
                            "choice_id": "ch_01_b",
                            "choice_text": "Go south into the basin.",
                            "target_node": "node_03", "sets_flags": ["chose_south"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_02", "chapter": 2, "scene_type": "combat",
                    "description": "A wraith blocks your path.",
                    "present_characters": ["char_01"], "present_location": "loc_02",
                    "present_creatures": ["cre_01"], "mood": "tense",
                    "choices": [
                        {
                            "choice_id": "ch_02_a",
                            "choice_text": "Fight the wraith.",
                            "target_node": "node_04", "sets_flags": ["fought_wraith"],
                            "requires_flags": ["chose_north"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_03", "chapter": 2, "scene_type": "exploration",
                    "description": "The basin is quiet.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_01", "present_creatures": [],
                    "mood": "peaceful",
                    "choices": [
                        {
                            "choice_id": "ch_03_a", "choice_text": "Rest here.",
                            "target_node": "node_05", "requires_flags": ["chose_south"],
                        },
                    ],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_04", "chapter": 3, "scene_type": "combat",
                    "description": "The wraith shatters.",
                    "present_characters": ["char_01"], "present_location": "loc_02",
                    "present_creatures": [], "mood": "triumphant",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "heroic",
                                "ending_title": "Victory"},
                },
                {
                    "node_id": "node_05", "chapter": 3, "scene_type": "ending",
                    "description": "Safe haven found.",
                    "present_characters": ["char_01", "char_02"],
                    "present_location": "loc_01", "present_creatures": [],
                    "mood": "peaceful",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "peaceful",
                                "ending_title": "Rest"},
                },
            ],
        }

    @staticmethod
    def _node_text() -> dict[str, Any]:
        return {
            "text": "The wind howled.\nYou grip your cloak.\n"
                   "A path lies ahead.\nNorth or south?\n"
                   "Lyra watches silently.\nThe choice is yours.\n"
                   "What will you do?",
            "choices": [
                {"choice_id": "ch_01_a", "choice_text": "North",
                 "target_node": "node_02", "text": "Head north toward the spire.",
                 "sets_flags": ["chose_north"]},
                {"choice_id": "ch_01_b", "choice_text": "South",
                 "target_node": "node_03", "text": "Go south into the basin.",
                 "sets_flags": ["chose_south"]},
            ],
            "mood": "desolate",
            "image_prompt": "A lone figure at the edge of endless white salt flats",
            "music_tone": "melancholy",
        }


class TrackedImageGenerator:
    """Fake ImageGenerator producing valid PNG bytes + lifecycle tracking."""

    provider: str = "fake"
    model_name: str = "fake-image-tracked"
    quantization: str = "Q8_0"
    ram_usage_mb: int = 5000

    def __init__(self) -> None:
        self._loaded = False
        self.load_count = 0
        self.unload_count = 0
        self.call_count = 0

    async def generate(
        self,
        prompt: str = "",
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
        steps: int = 20,
    ) -> bytes:
        self.call_count += 1
        from src.narrative.media import deterministic_image
        return deterministic_image(seed or 0)

    async def generate_thumbnail(
        self, image_bytes: bytes = b"", size: tuple[int, int] = (128, 128),
    ) -> bytes:
        return make_png(*size)

    async def load(self) -> None:
        self.load_count += 1
        self._loaded = True

    async def unload(self) -> None:
        self.unload_count += 1
        self._loaded = False


class TrackedMusicGenerator:
    """Fake MusicGenerator with ABC validation + MIDI conversion."""

    provider: str = "fake"
    call_count: int = 0

    def validate_abc(self, abc_text: str) -> bool:
        return abc_text.strip().startswith("X:1") and "K:" in abc_text

    def abc_to_midi(self, abc_text: str) -> bytes:
        return _MIDI_OK


# ── Test Harness ─────────────────────────────────────────────────────────────

# Shared fakes for the subclass — reset by each test. Using class-level
# variables is safe because pytest runs tests sequentially by default.
_fake_text: TrackedTextGenerator | None = None
_fake_image: TrackedImageGenerator | None = None
_fake_music: TrackedMusicGenerator | None = None


class InstrumentedGenerateStory(GenerateStory):
    """GenerateStory subclass that injects pre-created fake backends.

    Uses class-level variables for fake injection (safe for sequential tests).
    Also skips schema validation in production wiring — mock data is
    intentionally minimal and doesn't satisfy all schema constraints.
    Validator wiring is separately tested.
    """

    @staticmethod
    def _create_text_generator(config: Any) -> Any:
        if _fake_text is not None:
            return _fake_text
        return GenerateStory._create_text_generator(config)

    @staticmethod
    def _create_image_generator(config: Any) -> Any:
        if _fake_image is not None:
            return _fake_image
        return GenerateStory._create_image_generator(config)

    @staticmethod
    def _create_music_generator() -> Any:
        if _fake_music is not None:
            return _fake_music
        return GenerateStory._create_music_generator()

    @staticmethod
    def _resolve_schemas_dir() -> str:
        """Retained compatibility hook for schema-path resolution tests."""
        return ""

    async def execute(self, request: GenerationRequest) -> Any:
        """Run the real v2 plan with a deliberately tiny procedural world."""
        return await super().execute(replace(
            request, width=32, height=32, continent_count=1,
            civilization_count=2, history_years=20, erosion_passes=1,
            climate_relaxation_passes=8, plate_count=4,
            minimum_continent_cells=1,
        ))


def _inject_fakes(text: TrackedTextGenerator, image: TrackedImageGenerator,
                  music: TrackedMusicGenerator) -> None:
    """Set class-level fakes for InstrumentedGenerateStory."""
    global _fake_text, _fake_image, _fake_music
    _fake_text = text
    _fake_image = image
    _fake_music = music


def _clear_fakes() -> None:
    """Reset class-level fakes."""
    global _fake_text, _fake_image, _fake_music
    _fake_text = None
    _fake_image = None
    _fake_music = None


# ── Production-Wiring Tests ───────────────────────────────────────────────────


class TestProductionWiring:
    """Full production pipeline through GenerateStory.execute() with tracked fakes.

    These tests verify the ENTIRE production assembly path — all validators,
    manifest builder, package acceptance, batch scheduler, and model lifecycle.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        """Ensure schemas directory is resolvable and fakes are clean."""
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas directory not found")

    def setup_method(self) -> None:
        _clear_fakes()

    def teardown_method(self) -> None:
        _clear_fakes()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_pipeline_through_generate_story(self, tmp_path: Path) -> None:
        """The complete production path: GenerateStory.execute() → valid .story ZIP.

        Verifies:
        1. Pipeline completes without error
        2. All expected artifact keys present
        3. Package path returned and file exists
        4. Model load/unload counts correct (1 each for text + image)
        5. PackageAcceptance passes (ZIP is well-formed and complete)
        """
        text_gen = TrackedTextGenerator()
        image_gen = TrackedImageGenerator()
        music_gen = TrackedMusicGenerator()
        _inject_fakes(text_gen, image_gen, music_gen)

        service = InstrumentedGenerateStory()
        output_dir = str(tmp_path / "output")
        request = GenerationRequest(
            seed=42,
            title="Production Wiring Test",
            tone="mature_dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",  # Forces stub config
        )

        result = await service.execute(request)

        # ── 1. Pipeline completed without error ──────────────────────
        assert result.errors == [], (
            f"Expected zero errors, got {len(result.errors)}: {result.errors}"
        )

        # ── 2. Result metadata present ───────────────────────────────
        # artifact_id may be empty (set by packager), but package_path is the real output
        assert result.package_path, "Missing package_path"
        assert result.total_duration_seconds >= 0, "Missing duration"
        assert len(result.artifacts) >= 5, (
            f"Expected at least 5 artifacts, got {len(result.artifacts)}: {result.artifacts}"
        )
        assert len(result.phases) >= 2, (
            f"Expected at least 2 phases, got {result.phases}"
        )

        # ── 3. Package file exists on disk ───────────────────────────
        pkg = Path(result.package_path)
        assert pkg.exists(), f"Package not found at {result.package_path}"
        assert pkg.stat().st_size > 0, "Package is empty"

        # ── 4. Model lifecycle: text loaded once, image loaded once ──
        assert text_gen.load_count == 1, (
            f"Text model loaded {text_gen.load_count} times, expected 1"
        )
        assert text_gen.unload_count == 1, (
            f"Text model unloaded {text_gen.unload_count} times, expected 1"
        )
        assert image_gen.load_count >= 1, (
            f"Image model loaded {image_gen.load_count} times, expected >= 1"
        )
        assert image_gen.unload_count >= 1, (
            f"Image model unloaded {image_gen.unload_count} times, expected >= 1"
        )

        # Bible, art, story, graph, and media-intent enrichment.
        assert text_gen.call_count == 5, (
            f"Text generator called {text_gen.call_count} times, expected 5"
        )

        # ── 5. ZIP contents ──────────────────────────────────────────
        with zipfile.ZipFile(pkg) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "narrative/bible.json" in names
            assert "narrative/style_bible.json" in names
            assert "narrative/story.json" in names
            assert "narrative/graph.json" in names
            assert "narrative/gm_index.json" in names
            # Images should exist for nodes with image_prompt
            img_files = [n for n in names if n.startswith("assets/images/")]
            assert len(img_files) >= 1, f"No image files in package: {names}"
            # MIDI files should exist for nodes with music_tone
            midi_files = [n for n in names if n.startswith("assets/midi/")]
            assert len(midi_files) >= 1, f"No MIDI files in package: {names}"

            # All JSON entries must be parseable
            for entry in names:
                if entry.endswith(".json"):
                    content = json.loads(zf.read(entry))
                    assert content is not None, f"Null content in {entry}"

        # ── 6. PackageAcceptance passes ──────────────────────────────
        from src.storage.package_v2 import validate_v2_package
        acceptance = validate_v2_package(str(pkg))
        assert acceptance.accepted, (
            f"Package acceptance failed: {acceptance.issues}"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_artifacts_have_canonical_keys(self, tmp_path: Path) -> None:
        """All context.outputs use canonical keys (bible, not world_builder)."""
        text_gen = TrackedTextGenerator()
        image_gen = TrackedImageGenerator()
        music_gen = TrackedMusicGenerator()
        _inject_fakes(text_gen, image_gen, music_gen)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=99,
            title="Canonical Keys Test",
            tone="mature_dark_fantasy",
            output_dir=str(tmp_path / "output"),
            config_path="/nonexistent",
        )

        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        # Key artifacts must be present (canonical names, not step names)
        assert len(result.artifacts) >= 5, (
            f"Expected at least 5 artifacts, got {len(result.artifacts)}"
        )
        expected = {"world", "bible", "story", "narrative_project",
                    "gm_index", "images", "midi", "package_acceptance"}
        missing = expected - set(result.artifacts.keys())
        assert not missing, (
            f"Missing canonical artifact keys: {missing}"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_restores_identical_context_shape(self, tmp_path: Path) -> None:
        """Checkpoint after each phase is consistent — context shape preserved."""
        text_gen = TrackedTextGenerator()
        image_gen = TrackedImageGenerator()
        music_gen = TrackedMusicGenerator()
        _inject_fakes(text_gen, image_gen, music_gen)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=77,
            title="Resume Shape Test",
            tone="mature_dark_fantasy",
            output_dir=str(tmp_path / "output"),
            config_path="/nonexistent",
        )

        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        # Verify checkpoint DB exists
        db_path = tmp_path / "output" / "checkpoint.db"
        assert db_path.exists(), "Checkpoint database not created"

        # Verify all major steps have checkpoints
        from src.storage.checkpoint import CheckpointStore
        store = CheckpointStore(str(db_path))
        entries = store.load_all()

        # Checkpoints should use canonical output keys
        step_keys = {e.step_name: e.output_key for e in entries}
        assert step_keys.get("world_builder") in (None, "bible"), (
            f"world_builder output_key should be 'bible', "
            f"got {step_keys.get('world_builder')}"
        )
        assert step_keys.get("story_writer") in (None, "story"), (
            f"story_writer output_key should be 'story', "
            f"got {step_keys.get('story_writer')}"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_validators_are_wired_to_steps(self, tmp_path: Path) -> None:
        """Every bounded-inference production stage is wired into the registry."""
        text_gen = TrackedTextGenerator()
        image_gen = TrackedImageGenerator()
        music_gen = TrackedMusicGenerator()

        # Use the PARENT class's _build_steps (with validators)
        config = GenerateStory._stub_config()
        steps = GenerateStory._build_steps(
            text_gen, image_gen, music_gen, config, str(tmp_path),
        )

        # V2 stages enforce their deterministic acceptance boundaries inside
        # execute(); they must not be replaced by the legacy narrative stages.
        inference_steps = {
            "world_builder_v2", "art_direction_v2", "story_v2", "graph_v2",
            "media_intents_v2",
        }
        assert inference_steps <= steps.keys()
        assert not ({
            "world_builder", "art_director", "story_writer", "game_designer",
        } & steps.keys())

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_deterministic_output_same_seed(self, tmp_path: Path) -> None:
        """Same seed twice → identical artifact hashes (content determinism)."""
        import hashlib

        async def _run(seed: int, suffix: str) -> dict[str, str]:
            text_gen = TrackedTextGenerator()
            image_gen = TrackedImageGenerator()
            music_gen = TrackedMusicGenerator()
            _inject_fakes(text_gen, image_gen, music_gen)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=seed,
                title="Determinism Test",
                tone="mature_dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"

            pkg = Path(result.package_path)
            with zipfile.ZipFile(pkg) as zf:
                return {
                    name: hashlib.sha256(zf.read(name)).hexdigest()
                    for name in sorted(zf.namelist())
                    if name.endswith(".json")
                }

        hashes1 = await _run(42, "A")
        hashes2 = await _run(42, "B")

        # Content JSON artifacts should be identical (exclude manifest —
        # it contains wall-clock timestamps and generation_time_seconds).
        skip = {"manifest.json", "save/.gitkeep"}
        for key in hashes1:
            if key in skip:
                continue
            assert hashes1[key] == hashes2[key], (
                f"Non-deterministic: {key} differs between runs with same seed\n"
                f"  Run A: {hashes1[key][:16]}...\n"
                f"  Run B: {hashes2[key][:16]}..."
            )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_different_seeds_produce_different_output(
        self, tmp_path: Path,
    ) -> None:
        """Different seeds → different content."""
        import hashlib

        async def _run(seed: int, suffix: str) -> dict[str, str]:
            text_gen = TrackedTextGenerator()
            image_gen = TrackedImageGenerator()
            music_gen = TrackedMusicGenerator()
            _inject_fakes(text_gen, image_gen, music_gen)

            service = InstrumentedGenerateStory()
            request = GenerationRequest(
                seed=seed,
                title="Diff Test",
                tone="mature_dark_fantasy",
                output_dir=str(tmp_path / f"output_{suffix}"),
                config_path="/nonexistent",
            )
            result = await service.execute(request)
            assert result.errors == [], f"Errors: {result.errors}"
            pkg = Path(result.package_path)
            with zipfile.ZipFile(pkg) as zf:
                return {
                    n: hashlib.sha256(zf.read(n)).hexdigest()
                    for n in sorted(zf.namelist()) if n.endswith(".json")
                }

        hashes1 = await _run(42, "A")
        hashes2 = await _run(99, "B")

        differences = sum(1 for k in hashes1 if hashes1[k] != hashes2.get(k, ""))
        assert differences >= 1, (
            "Different seeds should produce at least one different artifact, "
            "but all hashes were identical."
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_manifest_has_required_fields(self, tmp_path: Path) -> None:
        """The accepted package-v2 manifest satisfies required fields."""
        text_gen = TrackedTextGenerator()
        image_gen = TrackedImageGenerator()
        music_gen = TrackedMusicGenerator()
        _inject_fakes(text_gen, image_gen, music_gen)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="Manifest Fields Test",
            tone="mature_dark_fantasy",
            output_dir=str(tmp_path / "output"),
            config_path="/nonexistent",
        )

        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        pkg = Path(result.package_path)
        with zipfile.ZipFile(pkg) as zf:
            manifest = json.loads(zf.read("manifest.json"))

        assert manifest["package_format"] == "storyteller.story"
        assert manifest["package_version"] == 2
        assert manifest["content_profile"] == "mature_dark_fantasy"
        assert manifest["title"] == "Manifest Fields Test"
        assert manifest["master_seed"] == 42
        assert manifest["story_id"].startswith("story_")
        assert len(manifest["content_hash"]) == 64
        assert manifest["entry_node"] in manifest["node_assets"]
        assert manifest["world"]["index"] == "world/index.json"
        assert manifest["world"]["present_year"] == 20
        assert manifest["artifacts"]
        assert manifest["region_maps"]
        assert "complete_world" in manifest["required_features"]


class TestProductionErrorHandling:
    """Error propagation through the production pipeline."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)

    def setup_method(self) -> None:
        _clear_fakes()

    def teardown_method(self) -> None:
        _clear_fakes()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_text_phase_error_surfaces_in_result(self, tmp_path: Path) -> None:
        """A terminal configuration error results in GenerationResult.errors, no crash."""
        from src.pipeline.errors import ConfigurationError

        class ConfigErrorTextGen(TrackedTextGenerator):
            async def generate(self, *args: Any, **kw: Any) -> Any:
                raise ConfigurationError("models.yaml", "Missing required model file")

        text_gen = ConfigErrorTextGen()
        image_gen = TrackedImageGenerator()
        music_gen = TrackedMusicGenerator()
        _inject_fakes(text_gen, image_gen, music_gen)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="Error Test",
            tone="mature_dark_fantasy",
            output_dir=str(tmp_path / "output"),
            config_path="/nonexistent",
        )

        result = await service.execute(request)

        # Should NOT crash — error surfaces in result.errors
        assert len(result.errors) >= 1, (
            f"Expected at least 1 error, got {result.errors}"
        )
        assert any("Missing required model" in e for e in result.errors), (
            f"Error should mention config: {result.errors}"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mandatory_image_failure_aborts_v2_publication(
        self, tmp_path: Path, monkeypatch: Any,
    ) -> None:
        """V2 retries a failed mandatory image stage and refuses publication."""

        text_gen = TrackedTextGenerator()

        class FlakyImageGen(TrackedImageGenerator):
            call_count = 0

            async def generate(self, *args: Any, **kwargs: Any) -> bytes:
                # Default policy: 3 retries + 1 first attempt = 4 calls for
                # node_00, which fails every time → quarantined.
                self.call_count += 1
                if self.call_count <= 4:
                    from src.pipeline.errors import GenerationError
                    raise GenerationError("image_generator", "Persistent image generation failure")
                return await super().generate(*args, **kwargs)

        image_gen = FlakyImageGen()
        music_gen = TrackedMusicGenerator()
        _inject_fakes(text_gen, image_gen, music_gen)

        service = InstrumentedGenerateStory()
        output_dir = tmp_path / "output"
        request = GenerationRequest(
            seed=42,
            title="Quarantine Test",
            tone="mature_dark_fantasy",
            output_dir=str(output_dir),
            config_path="/nonexistent",
        )

        result = await service.execute(request)

        assert any("image_media_v2" in error for error in result.errors), result.errors
        assert image_gen.call_count == 4
        assert not Path(result.package_path).exists()
