"""Production entry points may expose only the procedural-first service plan."""
from pathlib import Path

from src.application.generate_story import GenerateStory
from src.application.models import GenerationRequest
from src.domain.run_spec import RunSpec, WorldSpec
from src.pipeline.plan import PipelinePlan


def test_generation_request_rebuilds_lossless_resume_request() -> None:
    spec = RunSpec(seed=91, title="Locked", temperature=0.3,
                   world=WorldSpec(width=96, height=64, plate_count=7,
                                   minimum_continent_cells=32, local_z_levels=20))
    request = GenerationRequest.from_run_spec(
        spec, config_path="models.yaml", output_dir="run", resume=True,
    )
    assert request.to_run_spec() == spec
    assert request.config_path == "models.yaml"
    assert request.output_dir == "run"
    assert request.resume is True


def test_base_service_registry_exactly_matches_production_v2() -> None:
    plan = PipelinePlan.production_v2()
    steps = GenerateStory._build_steps(
        None, None, None, GenerateStory._stub_config(), "tmp/fence",
    )
    assert list(steps) == plan.step_ids()
    forbidden = {
        "world_builder", "art_director", "story_writer", "game_designer",
        "music_generator", "image_generator", "indexer", "narrative_v2",
    }
    assert forbidden.isdisjoint(steps)


def test_legacy_plan_factory_is_deleted() -> None:
    assert not hasattr(PipelinePlan, "standard")


def test_product_entrypoints_call_shared_generate_story_service() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("src/cli.py", "scripts/run_overnight.py"):
        source = (root / relative).read_text()
        assert "GenerateStory()" in source
        assert "GenerationRequest" in source
        assert "PipelinePlan.standard()" not in source


def test_runtime_and_doc_generator_do_not_reference_legacy_plan_factory() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("src", "scripts"):
        for path in (root / relative).rglob("*.py"):
            assert "PipelinePlan.standard" not in path.read_text(), path


def test_runtime_and_scripts_do_not_import_absorbed_v1_steps() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = (
        "models.world_builder", "models.art_director", "models.story_writer",
        "models.game_designer", "models.image_generator_step",
        "models.music_generator_step", "storage.indexer",
        "storage.orchestrator", "storage.manifest_builder", "storage.packager",
    )
    for relative in ("src", "scripts"):
        for path in (root / relative).rglob("*.py"):
            if path.name in {
                "world_builder.py", "art_director.py", "story_writer.py",
                "game_designer.py", "image_generator_step.py",
                "music_generator_step.py", "indexer.py", "orchestrator.py",
                "manifest_builder.py", "packager.py",
            }:
                continue
            source = path.read_text()
            assert not any(name in source for name in forbidden), path


def test_legacy_storage_orchestrator_is_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/storage/orchestrator.py").exists()


def test_legacy_gm_indexer_is_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/storage/indexer.py").exists()


def test_legacy_packager_is_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/storage/packager.py").exists()


def test_legacy_manifest_builder_is_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/storage/manifest_builder.py").exists()


def test_narrative_first_text_adapters_are_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("world_builder.py", "art_director.py", "story_writer.py", "game_designer.py",
                 "bible_helpers.py"):
        assert not (root / "src/models" / name).exists()
    assert not (root / "tests/test_resume_verification.py").exists()


def test_v1_media_adapters_are_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    for name in ("image_generator_step.py", "music_generator_step.py"):
        assert not (root / "src/models" / name).exists()
    for name in ("test_image_generator_step.py", "test_music_generator_step.py"):
        assert not (root / "tests" / name).exists()


def test_v1_archive_determinism_harness_is_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "tests/test_phase56d.py").exists()
