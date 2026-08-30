"""P8.C0 procedural-first production wiring."""
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.application.generate_story import GenerateStory
from src.application.models import GenerationRequest
from src.config import AppConfig
from src.domain.run_spec import RunSpec
from src.pipeline.plan import PipelinePlan
from src.storage.package_v2 import validate_v2_package
from src.storage.project_v2 import package_project_v2
from src.application.v2_steps import (AcceptPackageV2Stage, ArtDirectionV2Stage,
                                      BibleV2Stage, PackageV2Stage, PublishPackageV2Stage)
from src.world.views import WorldView


def test_request_converts_every_world_field_once() -> None:
    request = GenerationRequest(seed=7, plate_count=31, sea_level_ppm=400_000,
                                local_z_levels=48)
    spec = request.to_run_spec()
    assert spec.tone == "mature_dark_fantasy"
    assert spec.world.plate_count == 31
    assert spec.world.sea_level_ppm == 400_000
    assert spec.world.local_z_levels == 48
    assert GenerationRequest(seed=7).to_run_spec() == GenerationRequest(seed=7).to_run_spec()


def test_production_plan_is_procedural_first_and_terminal() -> None:
    plan = PipelinePlan.production_v2(); plan.validate()
    assert plan.step_ids() == ["physical_world", "simulate_world", "local_maps_v2",
                               "world_builder_v2", "reconcile_world", "art_direction_v2", "story_v2", "graph_v2",
                               "media_intents_v2", "image_media_v2",
                               "music_media_v2", "accept_media_v2", "gm_index_v2", "package_v2",
                               "accept_package_v2", "packager"]
    assert all(step.failure_policy == "abort" for step in plan)
    assert plan.get("world_builder_v2").requires == ("world",)
    assert "reconciliation" in plan.get("package_v2").requires


def test_generate_story_uses_production_v2_plan() -> None:
    """The canonical GenerateStory service resolves the production_v2 plan."""
    plan = GenerateStory._build_plan()
    plan.validate()
    assert plan.step_ids() == [
        "physical_world", "simulate_world", "local_maps_v2", "world_builder_v2",
        "reconcile_world", "art_direction_v2", "story_v2", "graph_v2",
        "media_intents_v2", "image_media_v2", "music_media_v2", "accept_media_v2",
        "gm_index_v2", "package_v2", "accept_package_v2", "packager",
    ]
    # Every v2 stage is terminal (no quarantine at publication)
    assert all(step.failure_policy == "abort" for step in plan)
    # World must precede Bible; reconciliation requires both
    assert plan.get("world_builder_v2").requires == ("world",)
    assert set(plan.get("art_direction_v2").requires) == {
        "world", "bible", "reconciliation",
    }
    # Packager requires the complete chain
    package = plan.get("package_v2")
    assert "narrative_project" in package.requires
    assert "world" in package.requires
    assert "style_bible" in package.requires
    assert {"local_maps", "media", "gm_index"} <= set(package.requires)
    assert plan.get("accept_package_v2").requires == ("package_candidate",)
    assert plan[-1].requires == ("package_candidate", "package_acceptance")


def test_generate_story_step_keys_match_production_plan() -> None:
    """Every step ID in the production plan has a registered implementation."""
    plan = PipelinePlan.production_v2()
    config = GenerateStory._stub_config()
    steps = GenerateStory._build_steps(None, None, None, config, "tmp/out")
    missing = [spec.id for spec in plan if spec.id not in steps]
    assert not missing, f"Plan steps without implementation: {missing}"
    assert set(steps) == set(plan.step_ids()), "Base registry must not expose legacy production steps"


def test_stage_outputs_publish_an_accepted_v2_package(tmp_path: Path, phase5_project) -> None:
    world, bible, narrative = phase5_project
    target = tmp_path / "integrated.story"
    package_project_v2(world, bible, narrative, target, title="Integrated", seed=17)
    result = validate_v2_package(target)
    assert result.accepted, result.issues
    assert result.manifest is not None
    assert result.manifest["content_profile"] == "mature_dark_fantasy"
    assert any(item["path"].startswith("world/source/") for item in result.manifest["artifacts"])
    artifacts = result.manifest["artifacts"]
    assert all(set(item) >= {"artifact_id", "kind", "path", "sha256", "size_bytes",
                                  "depends_on", "producer"} for item in artifacts)
    assert all(set(item["producer"]) >= {"component", "algorithm_version", "fingerprint",
                                              "code_revision", "schema_sha256"}
               for item in artifacts)
    assert len({item["path"] for item in artifacts}) == len(artifacts)
    assert len({item["artifact_id"] for item in artifacts}) == len(artifacts)
    with zipfile.ZipFile(target) as archive:
        ledger = json.loads(archive.read("world/source/coverage.json"))
        source_paths = {name for name in archive.namelist()
                        if name.startswith("world/source/") and name != "world/source/coverage.json"}
        assert {item["archive_path"] for item in ledger["sources"]} == source_paths
        graph = json.loads(archive.read("narrative/graph.json"))
        narrative_refs = {ref for node in graph["nodes"] for ref in node["authoritative_refs"]}
        assert any(item["artifact_id"] not in narrative_refs for item in ledger["sources"])
        history_index = json.loads(archive.read("world/history/index.json"))
        event_years = [
            int(json.loads(archive.read(path))["year"])
            for path in history_index["events"]
        ]
        for path in history_index["snapshots"]:
            snapshot = json.loads(archive.read(path))
            assert snapshot["ledger_position"] == sum(
                1 for year in event_years if year <= int(snapshot["year"])
            )
            assert isinstance(snapshot["state"], dict)


@pytest.mark.asyncio
async def test_staged_package_is_invisible_until_acceptance_and_unchanged_publish(
    tmp_path: Path, phase5_project: Any,
) -> None:
    world, bible, narrative = phase5_project
    outputs: dict[str, Any] = {
        "world": {"path": str(world)}, "bible": {"root": str(bible)},
        "narrative_project": {"path": str(narrative)},
        "local_maps": {"root": str(narrative)},
    }
    context = SimpleNamespace(outputs=outputs, title="Staged", seed=17)
    candidate = await PackageV2Stage(
        "package_v2", "package_candidate", str(tmp_path),
    ).generate(context)
    outputs["package_candidate"] = candidate.data

    final = tmp_path / "output.story"
    assert not final.exists()
    assert Path(candidate.data["package_path"]).name.startswith(".")

    acceptance = await AcceptPackageV2Stage(
        "accept_package_v2", "package_acceptance", str(tmp_path),
    ).generate(context)
    outputs["package_acceptance"] = acceptance.data
    Path(candidate.data["package_path"]).write_bytes(b"changed after acceptance")

    with pytest.raises(ValueError, match="PACKAGE_CHANGED_AFTER_ACCEPTANCE"):
        await PublishPackageV2Stage("packager", "packager", str(tmp_path)).generate(context)
    assert not final.exists()


@pytest.mark.asyncio
async def test_v2_package_identity_is_content_derived_and_publish_is_atomic(
    tmp_path: Path, phase5_project: Any, monkeypatch: Any,
) -> None:
    """Identical inputs keep identity stable and publication uses os.replace."""
    import os
    world, bible, narrative = phase5_project

    async def stage(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        outputs: dict[str, Any] = {
            "world": {"path": str(world)}, "bible": {"root": str(bible)},
            "narrative_project": {"path": str(narrative)},
            "local_maps": {"root": str(narrative)},
        }
        context = SimpleNamespace(outputs=outputs, title="Identity", seed=17)
        candidate = await PackageV2Stage("package_v2", "package_candidate", str(root)).generate(context)
        outputs["package_candidate"] = candidate.data
        accepted = await AcceptPackageV2Stage(
            "accept_package_v2", "package_acceptance", str(root),
        ).generate(context)
        return outputs, accepted.data

    first_outputs, first_acceptance = await stage(tmp_path / "first")
    _, second_acceptance = await stage(tmp_path / "second")
    assert first_acceptance["story_id"] == second_acceptance["story_id"]
    assert first_acceptance["content_hash"] == second_acceptance["content_hash"]
    assert first_acceptance["story_id"] == f"story_{first_acceptance['content_hash'][:32]}"

    calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def tracking_replace(source: Any, destination: Any) -> None:
        calls.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", tracking_replace)
    first_outputs["package_acceptance"] = first_acceptance
    context = SimpleNamespace(outputs=first_outputs, title="Identity", seed=17)
    published = await PublishPackageV2Stage("packager", "packager", str(tmp_path / "first")).generate(context)
    destination = Path(published.data["package_path"])
    assert destination.is_file()
    assert any(target == destination for _, target in calls)
    assert not Path(first_acceptance["package_path"]).exists()


@pytest.mark.asyncio
async def test_bible_model_can_enrich_but_cannot_replace_world_facts(
    tmp_path: Path, phase4_world: Path,
) -> None:
    class MaliciousEnricher:
        async def generate(self, **kwargs: Any) -> dict[str, Any]:
            return {
                "present_year": -999,
                "regions": [],
                "history": [],
                "interpretations": ["Documented ruins suggest a culture shaped by loss."],
            }

    before = WorldView(phase4_world).file_hashes
    context = SimpleNamespace(
        outputs={"world": {"path": str(phase4_world)}},
        title="Immutable World",
        seed=17,
        spec=GenerationRequest(seed=17).to_run_spec(),
    )
    stage = BibleV2Stage(
        "world_builder_v2", "bible", str(tmp_path), generator=MaliciousEnricher(),
    )
    output = await stage.generate(context)
    bible = json.loads(Path(output.data["path"]).read_text())

    assert bible["present_year"] == WorldView(phase4_world).present_year
    assert bible["regions"]
    assert bible["history"]
    assert bible["interpretations"] == [
        "Documented ruins suggest a culture shaped by loss.",
    ]
    assert WorldView(phase4_world).file_hashes == before


@pytest.mark.asyncio
async def test_art_model_cannot_replace_authoritative_art_references(
    tmp_path: Path, phase5_project: Any,
) -> None:
    world, bible_root, _ = phase5_project

    class MaliciousArtModel:
        async def generate(self, **kwargs: Any) -> dict[str, Any]:
            payload = json.loads(kwargs["prompt"].split("\n", 1)[1])
            return {
                "map_artifact_id": "forged",
                "climate_palettes": payload["climate_palettes"],
                "culture_motifs": payload["culture_motifs"],
            }

    context = SimpleNamespace(
        outputs={
            "world": {"path": str(world)},
            "bible": {"path": str(bible_root / "bible.json"), "root": str(bible_root)},
            "reconciliation": {"accepted": True},
        },
        seed=17,
        spec=GenerationRequest(seed=17).to_run_spec(),
    )
    stage = ArtDirectionV2Stage(
        "art_direction_v2", "style_bible", str(tmp_path), generator=MaliciousArtModel(),
    )
    with pytest.raises(ValueError, match="ART-DIRECTION-SHAPE"):
        await stage.generate(context)


def test_media_intents_cannot_replace_deterministic_seeds(phase5_project: Any) -> None:
    from src.narrative.pipeline import _graph_from_dict, write_media_intents
    _, _, narrative = phase5_project
    graph = _graph_from_dict(json.loads((narrative / "graph.json").read_text()))
    forged = {node.node_id: {
        "image_prompt": node.media_intent.image_prompt,
        "music_mood": node.media_intent.music_mood,
        "image_seed": -1,
    } for node in graph.nodes}
    with pytest.raises(ValueError, match="MEDIA-INTENT-SHAPE"):
        write_media_intents(narrative, forged)


# ── P8.C0: GenerateStory.execute() through the production_v2 plan ────────


class _NoopBackend:
    """Fake backend that provides load/unload without real models."""
    provider = "fake"
    model_name = "noop"
    quantization = ""
    ram_usage_mb = 0
    def __init__(self) -> None:
        self.generate_count = 0
    async def generate(self, **kw: Any) -> Any:
        self.generate_count += 1
        prompt = kw.get("prompt", "")
        if "size" in kw:
            from src.narrative.media import deterministic_image
            return deterministic_image(kw.get("seed", 0))
        if "Refine the visual wording" in prompt:
            payload = json.loads(prompt.split("\n", 1)[1])
            return {
                "climate_palettes": {key: f"Refined {value}"
                                     for key, value in payload["climate_palettes"].items()},
                "culture_motifs": {key: f"Refined {value}"
                                   for key, value in payload["culture_motifs"].items()},
            }
        if "exactly these scene IDs" in prompt:
            ids = re.findall(r'\"scene_id\":\"([^\"]+)\"', prompt)
            return {"scenes": {scene_id: {
                "title": f"The Weight of {scene_id}",
                "summary": f"Documented pressures converge in scene {scene_id}.",
            } for scene_id in ids}}
        if "exactly these IDs" in prompt:
            ids = re.findall(r'\"node_id\":\"([^\"]+)\"', prompt)
            return {"nodes": {node_id: f"Documented tensions sharpen at node {node_id}."
                              for node_id in ids}}
        if "Refine the image prompt and music mood" in prompt:
            source = json.loads(prompt.split("\n", 1)[1])
            return {"nodes": {node_id: {
                "image_prompt": f"Refined {value['image_prompt']}",
                "music_mood": f"Refined {value['music_mood']}",
            } for node_id, value in source.items()}}
        return {"interpretations": ["Ash and old vows shape the documented age."]}
    async def load(self) -> None: pass
    async def unload(self) -> None: pass


class _V2SmokeGenerateStory(GenerateStory):
    """GenerateStory subclass that injects no-op fakes for the v2 plan.

    The world remains procedural and authoritative. A tracked text fake
    exercises the required model-enrichment boundary without loading GGUFs.
    """

    @staticmethod
    def _create_text_generator(config: AppConfig) -> Any:
        return _NoopBackend()

    @staticmethod
    def _create_image_generator(config: AppConfig) -> Any:
        return _NoopBackend()

    @staticmethod
    def _create_music_generator() -> Any:
        return _NoopBackend()

    @staticmethod
    def _create_validator(config: AppConfig) -> Any:
        return _NoopBackend()


@pytest.mark.asyncio
async def test_generate_story_execute_v2_produces_accepted_package(tmp_path: Path) -> None:
    """Full GenerateStory.execute() through production_v2 plan → valid .story.

    Uses a tiny 32x32 world with minimal erosion/climate passes and a short
    20-year history so the complete pipeline runs in seconds. Procedural facts
    remain deterministic; a fake text backend exercises the bounded Bible,
    story-prose, and graph-prose inference ports.
    """
    output_dir = tmp_path / "output"
    request = GenerationRequest(
        seed=17,
        title="V2 Smoke Test",
        tone="mature_dark_fantasy",
        width=32, height=32,
        continent_count=1,
        civilization_count=2,
        history_years=20,
        erosion_passes=1,
        climate_relaxation_passes=8,
        plate_count=4,
        minimum_continent_cells=1,
        output_dir=str(output_dir),
        config_path="/nonexistent",
    )

    service = _V2SmokeGenerateStory()
    result = await service.execute(request)

    assert not result.errors, f"Pipeline errors: {result.errors}"
    assert result.package_path, "No package produced"
    assert Path(result.package_path).exists(), f"Package missing: {result.package_path}"
    assert result.artifact_id, "No artifact ID"
    assert result.total_duration_seconds > 0, "No duration recorded"
    stored_run_spec = RunSpec.from_dict(json.loads((output_dir / "run_spec.json").read_text()))
    assert stored_run_spec == request.to_run_spec()

    acceptance = validate_v2_package(result.package_path)
    assert acceptance.accepted, [issue.message for issue in acceptance.issues]
    assert acceptance.manifest is not None
    assert acceptance.manifest.get("content_profile") == "mature_dark_fantasy"
