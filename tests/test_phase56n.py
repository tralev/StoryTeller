"""Phase 5.6N: Type composition boundaries.

Verifies:
  N1. ArtifactKey Literal + CANONICAL_ARTIFACT_KEYS + is_artifact_key()
  N2. StepOutput[DataT] is generic
  N3. TypedDict boundary models mirror the JSON schemas
  N4. RunSpec + PipelineContext typed accessors (tone/title/temperature)
  N5. Typed artifact repository methods on ArtifactStore
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

SCHEMAS_DIR = str(Path(__file__).resolve().parent.parent / "schemas")


# ── N1: ArtifactKey ───────────────────────────────────────────────────────────


class TestArtifactKey:
    """Canonical artifact keys are complete and validated."""

    EXPECTED_KEYS = {
        "world_snapshot", "bible", "style_bible", "story", "graph",
        "images", "midi", "gm_index", "manifest", "packager",
    }

    def test_canonical_keys_complete(self) -> None:
        from src.pipeline.artifacts import CANONICAL_ARTIFACT_KEYS

        assert CANONICAL_ARTIFACT_KEYS == self.EXPECTED_KEYS

    def test_is_artifact_key(self) -> None:
        from src.pipeline.artifacts import is_artifact_key

        assert is_artifact_key("bible")
        assert is_artifact_key("gm_index")
        assert not is_artifact_key("world_builder")  # step name, not artifact key
        assert not is_artifact_key("package_path")   # packager result field

    def test_step_key_maps_use_canonical_keys(self) -> None:
        """Step→artifact key maps reference canonical keys only."""
        from src.pipeline.artifacts import CANONICAL_ARTIFACT_KEYS
        from src.domain.artifacts import STEP_ARTIFACT_KEYS

        for step_name, key in STEP_ARTIFACT_KEYS.items():
            assert key in CANONICAL_ARTIFACT_KEYS, (
                f"{step_name} → {key!r} is not a canonical artifact key"
            )

    def test_pipeline_export(self) -> None:
        """ArtifactKey is re-exported from the pipeline package."""
        from src.pipeline import ArtifactKey, is_artifact_key  # noqa: F401

        assert is_artifact_key("story")


# ── N2: StepOutput generic ────────────────────────────────────────────────────


class TestStepOutputGeneric:
    """StepOutput[DataT] carries the payload type."""

    def test_bare_stepoutput_still_works(self) -> None:
        from src.models.base import StepOutput

        output = StepOutput(data={"bible": 1}, step_name="world_builder")
        assert output.data == {"bible": 1}
        assert output.step_name == "world_builder"

    def test_subscripted_stepoutput_constructs(self) -> None:
        from src.models.base import StepOutput
        from src.pipeline.artifacts import ManifestDict

        # Subscripting a Generic class returns a runtime alias whose
        # __call__ delegates to the origin — this must construct fine.
        output = StepOutput[ManifestDict](
            data={"schema_version": 1, "title": "X"},
            step_name="manifest_builder",
        )
        assert isinstance(output, StepOutput)
        assert output.data["title"] == "X"

    def test_manifest_builder_returns_typed_output(self) -> None:
        """ManifestBuilder.run() is annotated StepOutput[ManifestDict]."""
        import asyncio
        import inspect

        from src.job_queue import PipelineContext
        from src.models.base import StepOutput
        from src.storage.manifest_builder import ManifestBuilder

        sig = inspect.signature(ManifestBuilder.run)
        assert "StepOutput[ManifestDict]" in str(sig.return_annotation)

        from src.pipeline.artifacts import RunSpec
        ctx = PipelineContext(
            run_id="run_n2", seed=1,
            spec=RunSpec(seed=1, title="N2 Test", tone="dark_fantasy"),
        )
        ctx.state["start_time"] = __import__("time").time()
        output = asyncio.run(ManifestBuilder().run(ctx))
        assert isinstance(output, StepOutput)
        assert output.data["title"] == "N2 Test"


# ── N3: TypedDict boundary models ─────────────────────────────────────────────


class TestTypedDictBoundaries:
    """TypedDicts mirror the JSON schema shapes."""

    def test_choice_dict_round_trip(self) -> None:
        from src.pipeline.artifacts import ChoiceDict

        choice: ChoiceDict = {
            "choice_id": "ch_01_a",
            "choice_text": "Enter the cave",
            "target_node": "node_02",
            "sets_flags": ["met_shadow"],
        }
        # TypedDicts behave as dicts at runtime
        assert choice["choice_id"] == "ch_01_a"
        assert json.loads(json.dumps(choice)) == choice

    def test_graph_node_dict_shape(self) -> None:
        from src.pipeline.artifacts import GraphNodeDict

        node: GraphNodeDict = {
            "node_id": "node_01",
            "chapter": 1,
            "scene_type": "exploration",
            "text": "You stand at the crossroads.",
            "present_characters": ["char_01"],
            "present_location": "loc_01",
            "mood": "tense",
            "choices": [
                {"choice_id": "ch_01_a", "choice_text": "Go north", "target_node": "node_02"},
            ],
        }
        assert node["node_id"] == "node_01"
        assert isinstance(node["choices"][0], dict)

    def test_manifest_dict_validates_against_schema(self) -> None:
        """A ManifestDict built from required fields passes manifest.schema.json."""
        if not Path(SCHEMAS_DIR).exists():
            pytest.skip("Schemas not found")

        from src.pipeline.artifacts import ManifestDict
        from src.validators.schema_validator import SchemaValidator

        manifest: ManifestDict = {
            "schema_version": 1,
            "story_id": "7b2c3f4e-1111-4a9b-8c0d-2e3f4a5b6c7d",
            "title": "The Crystal Accord",
            "tone": "heroic_fantasy",
            "seed": 7,
            "generator_version": "0.1.0",
            "models_used": {
                "text_generator": "qwen2.5-7b-instruct-Q4_K_M",
                "validator": "phi-3.5-mini-instruct-Q4_K_M",
                "image_generator": "sdxl-turbo-Q8_0",
                "music_generator": "via-text",
            },
            "prompt_versions": {
                "world_builder": "v1",
                "story_writer": "v1",
                "game_designer": "v1",
                "art_director": "v1",
                "composer": "v1",
            },
            "entry_point": "node_01",
            "provenance": {
                "inventory": {
                    "bible": "world_a1b2c3d4",
                    "style_bible": "style_a1b2c3d4",
                    "story": "story_a1b2c3d4",
                    "graph": "graph_a1b2c3d4",
                    "images": "img_a1b2c3d4",
                    "midi": "mid_a1b2c3d4",
                    "gm_index": "gmindex_a1b2c3d4",
                },
                "depends_on": {
                    "style_bible": ["world_a1b2c3d4"],
                    "story": ["world_a1b2c3d4"],
                    "graph": ["story_a1b2c3d4"],
                    "images": ["graph_a1b2c3d4", "style_a1b2c3d4"],
                    "midi": ["graph_a1b2c3d4"],
                    "gm_index": ["world_a1b2c3d4", "graph_a1b2c3d4"],
                },
                "produced_by": {
                    "bible": {"model": "mock", "model_hash": "a1b2c3d4e5f6a7b8", "prompt_version": "v1"},
                    "style_bible": {"model": "mock", "model_hash": "a1b2c3d4e5f6a7b8", "prompt_version": "v1"},
                    "story": {"model": "mock", "model_hash": "a1b2c3d4e5f6a7b8", "prompt_version": "v1"},
                    "graph": {"model": "mock", "model_hash": "a1b2c3d4e5f6a7b8", "prompt_version": "v1"},
                    "images": {"model": "mock", "model_hash": "a1b2c3d4e5f6a7b8", "prompt_version": "v1"},
                    "midi": {"model": "mock", "model_hash": "a1b2c3d4e5f6a7b8", "prompt_version": "v1"},
                    "gm_index": {"model": "deterministic", "model_hash": "-", "prompt_version": "v1"},
                },
            },
            "files": {
                "bible": "content/bible.json",
                "story": "content/story.json",
                "graph": "content/graph.json",
                "gm_index": "content/gm_index.json",
                "images": "content/images/",
                "midi": "content/midi/",
            },
        }

        validator = SchemaValidator(SCHEMAS_DIR)
        result = validator.validate_manifest(manifest)  # synchronous
        assert result.is_valid, result.format_for_retry()

    def test_media_meta_dicts(self) -> None:
        from src.pipeline.artifacts import ImageMetaDict, MidiMetaDict

        img: ImageMetaDict = {
            "size": (512, 512),
            "seed": 1,
            "prompt": "a cave",
            "image_path": "/tmp/x.png",
            "thumb_path": "/tmp/x_t.png",
            "image_bytes": 1024,
        }
        mid: MidiMetaDict = {
            "abc_notation": "X:1",
            "midi_path": "/tmp/x.mid",
            "midi_bytes": 512,
            "music_tone": "mysterious",
            "seed": 2,
        }
        assert img["image_bytes"] == 1024
        assert mid["midi_path"].endswith(".mid")


# ── N4: RunSpec + typed accessors ─────────────────────────────────────────────


class TestRunSpecAccessors:
    """PipelineContext exposes typed tone/title/temperature accessors."""

    def test_spec_takes_precedence_over_state(self) -> None:
        from src.job_queue import PipelineContext
        from src.pipeline.artifacts import RunSpec

        ctx = PipelineContext(run_id="r", seed=1)
        ctx.state["tone"] = "grimdark"  # legacy state — must lose to spec
        ctx.spec = RunSpec(title="Spec Title", tone="heroic_fantasy", temperature=0.3)

        assert ctx.tone == "heroic_fantasy"
        assert ctx.title == "Spec Title"
        assert ctx.temperature == 0.3

    def test_state_cannot_override_implicit_spec(self) -> None:
        from src.job_queue import PipelineContext

        ctx = PipelineContext(run_id="r", seed=1)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "State Title"
        ctx.state["temperature"] = 0.9

        assert ctx.tone == "dark_fantasy"
        assert ctx.title == "Untitled World"
        assert ctx.temperature == 0.7

    def test_defaults_without_spec_or_state(self) -> None:
        from src.job_queue import PipelineContext

        ctx = PipelineContext(run_id="r", seed=1)
        assert ctx.tone == "dark_fantasy"
        assert ctx.title == "Untitled World"
        assert ctx.temperature == 0.7

    def test_run_spec_is_frozen(self) -> None:
        from src.pipeline.artifacts import RunSpec

        spec = RunSpec(title="T", tone="t", temperature=0.5)
        assert spec.title == "T"
        with pytest.raises(AttributeError):
            spec.title = "Changed"  # frozen dataclass (misc disabled for tests)

    def test_generate_story_sets_typed_spec(self, tmp_path: Path) -> None:
        """GenerateStory routes GenerationRequest through the typed spec."""
        import asyncio

        from src.application.generate_story import GenerateStory
        from src.application.models import GenerationRequest

        from .test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            TrackedTextGenerator,
            _clear_fakes,
            _inject_fakes,
        )

        _clear_fakes()
        _inject_fakes(
            TrackedTextGenerator(), TrackedImageGenerator(), TrackedMusicGenerator(),
        )
        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42, title="Typed Spec Title", tone="grimdark",
            temperature=0.4,
            output_dir=str(tmp_path / "output"), config_path="/nonexistent",
            resume=False,
        )
        result = asyncio.run(service.execute(request))
        assert not result.errors, f"Errors: {result.errors}"

        # The manifest title must flow from the typed spec
        manifest_path = tmp_path / "output" / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            assert manifest["title"] == "Typed Spec Title"
            assert manifest["tone"] == "grimdark"

    def test_world_builder_reads_typed_spec(self, tmp_path: Path) -> None:
        """WorldBuilder uses context.tone/title/temperature (spec path)."""
        import asyncio

        from src.job_queue import PipelineContext
        from src.models.world_builder import WorldBuilder
        from src.pipeline.artifacts import RunSpec

        from .test_production_wiring import (
            TrackedTextGenerator, _clear_fakes,
        )

        _clear_fakes()
        text_gen = TrackedTextGenerator()
        ctx = PipelineContext(run_id="r", seed=7, output_dir=str(tmp_path))
        ctx.spec = RunSpec(title="Spec World", tone="heroic_fantasy", temperature=0.5)

        output = asyncio.run(WorldBuilder(text_gen).generate(ctx))
        assert output.data["generation_params"]["title"] == "Spec World"
        assert output.data["generation_params"]["tone"] == "heroic_fantasy"
        assert output.data["generation_params"]["temperature"] == 0.5


# ── N5: Typed artifact repository methods ─────────────────────────────────────


class TestTypedArtifactRepository:
    """ArtifactStore typed accessors round-trip artifacts."""

    def test_in_memory_round_trip(self) -> None:
        from src.artifact_store import ArtifactStore
        from src.pipeline.artifacts import BibleDict

        store = ArtifactStore()  # in-memory

        assert store.get_bible() is None

        bible: BibleDict = {"schema_version": 1, "world_name": "Test World"}
        store.put_bible(bible)
        assert store.get_bible() == bible
        assert store["bible"] == bible

    def test_graph_round_trip(self) -> None:
        from src.artifact_store import ArtifactStore
        from src.pipeline.artifacts import GraphDict

        store = ArtifactStore()
        graph = cast(GraphDict, {"schema_version": 1, "nodes": [{"node_id": "node_01"}]})
        store.put_graph(graph)
        assert store.get_graph() == graph

    def test_non_dict_value_returns_none(self) -> None:
        from src.artifact_store import ArtifactStore

        store = ArtifactStore()
        store["manifest"] = "not-a-dict"
        assert store.get_manifest() is None

    def test_all_typed_methods_present(self) -> None:
        from src.artifact_store import ArtifactStore

        store = ArtifactStore()
        for name in [
            "get_bible", "put_bible",
            "get_style_bible", "put_style_bible",
            "get_story", "put_story",
            "get_graph", "put_graph",
            "get_gm_index", "put_gm_index",
            "get_manifest", "put_manifest",
            "get_images", "put_images",
            "get_midi", "put_midi",
            "get_world_snapshot", "put_world_snapshot",
            "get_packager", "put_packager",
        ]:
            assert callable(getattr(store, name)), name

    def test_disk_backed_round_trip(self, tmp_path: Path) -> None:
        from src.artifact_store import ArtifactStore

        out = tmp_path / "output"
        out.mkdir()

        store = ArtifactStore(output_dir=str(out))
        store.put_bible({"world_name": "Disk World"})
        store.put_manifest({"title": "Disk Title"})

        # A fresh store over the same dir reads back via typed accessors
        store2 = ArtifactStore(output_dir=str(out))
        assert store2.get_bible() == {"world_name": "Disk World"}
        assert store2.get_manifest() == {"title": "Disk Title"}

        # JSON files were flushed to disk
        assert (out / "bible.json").exists()
        assert (out / "manifest.json").exists()
