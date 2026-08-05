"""Phase 5.6X — Artifact Provenance.

Answers "why does this artifact exist?":

  X1: canonical content-derived artifact IDs in the manifest inventory
  X2: depends_on relationships (Bible → Story → Graph → Assets/Index)
  X3: model + prompt hashes per producing artifact (not only global)
  X4: dependency IDs used in checkpoint/resume invalidation
  X5: provenance consistency checks in PackageAcceptance
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.artifacts import ManifestDict
from src.storage.provenance import (
    DEPENDENCIES,
    artifact_id,
    build_depends_on,
    build_inventory,
    build_produced_by,
    build_provenance,
)


def _sample_outputs() -> dict[str, dict[str, Any]]:
    """Deterministic sample artifact dicts for provenance unit tests."""
    return {
        "bible": {"schema_version": 1, "world_name": "Test World", "seed": 42},
        "style_bible": {"schema_version": 1, "art_style": {"palette": "grey"}},
        "story": {"schema_version": 1, "chapters": [{"number": 1}]},
        "graph": {
            "schema_version": 1, "starting_node": "node_01",
            "nodes": [{"node_id": "node_01", "choices": []}],
        },
        "images": {"images": {"node_01": {"size": (512, 512)}}, "image_count": 1},
        "midi": {"midi": {"node_01": {"ticks": 96}}, "midi_count": 1},
        "gm_index": {"schema_version": 1, "entries": [], "keywords": {}},
    }


def _sample_models() -> dict[str, str]:
    return {
        "text_generator": "qwen2.5-7b-instruct-Q4_K_M",
        "validator": "phi-3.5-mini-instruct-Q4_K_M",
        "image_generator": "sdxl-turbo-Q8_0",
        "music_generator": "via-text",
    }


def _sample_prompts() -> dict[str, str]:
    return {
        "world_builder": "v1", "story_writer": "v1", "game_designer": "v1",
        "art_director": "v1", "composer": "v1", "style_bible": "v1",
    }


# ── X1: inventory ────────────────────────────────────────────────────────


class TestInventory:
    """X1: canonical content-derived artifact IDs."""

    def test_inventory_covers_all_canonical_artifacts(self) -> None:
        inv = build_inventory(_sample_outputs())
        assert set(inv.keys()) == {
            "bible", "style_bible", "story", "graph", "images", "midi", "gm_index",
        }

    def test_inventory_ids_match_step_algorithm(self) -> None:
        """ID = {prefix}_{sha256(json sort_keys)[:8]} — same as the steps."""
        outputs = _sample_outputs()
        inv = build_inventory(outputs)
        for key, data in outputs.items():
            assert inv[key] == artifact_id(key, data)
            # Prefixes match each generation step's _make_artifact_id
            assert inv[key].startswith({
                "bible": "world_", "style_bible": "style_", "story": "story_",
                "graph": "graph_", "images": "img_", "midi": "mid_",
                "gm_index": "gmindex_",
            }[key])

    def test_inventory_deterministic(self) -> None:
        inv1 = build_inventory(_sample_outputs())
        inv2 = build_inventory(_sample_outputs())
        assert inv1 == inv2

    def test_inventory_changes_when_content_changes(self) -> None:
        out = _sample_outputs()
        base = build_inventory(out)["bible"]
        out["bible"] = {"schema_version": 1, "world_name": "Changed", "seed": 42}
        changed = build_inventory(out)["bible"]
        assert base != changed

    def test_inventory_skips_non_dict_artifacts(self) -> None:
        inv = build_inventory({"bible": "not-a-dict"})
        assert "bible" not in inv


# ── X2: depends_on ───────────────────────────────────────────────────────


class TestDependsOn:
    """X2: dependency relationships recorded as upstream artifact IDs."""

    def test_dependency_graph_is_canonical(self) -> None:
        assert DEPENDENCIES == {
            "bible": [],
            "style_bible": ["bible"],
            "story": ["bible"],
            "graph": ["story"],
            "images": ["graph", "style_bible"],
            "midi": ["graph"],
            "gm_index": ["bible", "graph"],
        }

    def test_depends_on_resolves_to_inventory_ids(self) -> None:
        outputs = _sample_outputs()
        inv = build_inventory(outputs)
        depends = build_depends_on(inv)

        # Story depends on the exact bible artifact that produced it
        assert depends["story"] == [inv["bible"]]
        assert depends["graph"] == [inv["story"]]
        assert depends["images"] == [inv["graph"], inv["style_bible"]]
        assert depends["gm_index"] == [inv["bible"], inv["graph"]]
        assert depends["bible"] == []

    def test_depends_on_references_exist_in_inventory(self) -> None:
        inv = build_inventory(_sample_outputs())
        depends = build_depends_on(inv)
        known_ids = set(inv.values())
        for upstream_ids in depends.values():
            for up_id in upstream_ids:
                assert up_id in known_ids


# ── X3: produced_by ──────────────────────────────────────────────────────


class TestProducedBy:
    """X3: model + prompt hashes per producing artifact."""

    def test_every_artifact_has_producer(self) -> None:
        pb = build_produced_by(_sample_models(), _sample_prompts())
        assert set(pb.keys()) == {
            "bible", "style_bible", "story", "graph", "images", "midi", "gm_index",
        }
        for entry in pb.values():
            assert {"model", "model_hash", "prompt_version"} <= set(entry.keys())

    def test_text_artifacts_attributed_to_text_model(self) -> None:
        pb = build_produced_by(_sample_models(), _sample_prompts())
        for key in ["bible", "style_bible", "story", "graph", "midi"]:
            assert pb[key]["model"] == _sample_models()["text_generator"]
        assert pb["images"]["model"] == _sample_models()["image_generator"]
        assert pb["gm_index"]["model"] == "deterministic"

    def test_model_file_hash_used_when_provided(self) -> None:
        pb = build_produced_by(
            _sample_models(), _sample_prompts(),
            model_hashes={"text_generator": "deadbeef" * 4},
        )
        assert pb["story"]["model_hash"] == "deadbeef" * 4

    def test_model_hash_falls_back_to_identity_hash(self) -> None:
        pb = build_produced_by(_sample_models(), _sample_prompts())
        import hashlib
        expected = hashlib.sha256(
            _sample_models()["text_generator"].encode(),
        ).hexdigest()[:16]
        assert pb["story"]["model_hash"] == expected

    def test_prompt_version_recorded_per_artifact(self) -> None:
        pb = build_produced_by(_sample_models(), _sample_prompts())
        assert pb["bible"]["prompt_version"] == "v1"
        assert pb["story"]["prompt_version"] == "v1"


# ── X4: dependency-ID resume invalidation ────────────────────────────────


class TestCheckpointDependencyIds:
    """X4: checkpoints record dependency IDs; stale downstream is dropped."""

    def test_checkpoint_store_roundtrips_depends_on(self) -> None:
        from src.storage.checkpoint import CheckpointStore
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            store = CheckpointStore(path)
            store.save(
                "story_writer", phase=3, seed=42,
                output={"chapters": []},
                depends_on={"bible": "world_a1b2c3d4"},
            )
            entry = store.load("story_writer")
            assert entry is not None
            assert entry.depends_on == {"bible": "world_a1b2c3d4"}
        finally:
            Path(path).unlink(missing_ok=True)

    def test_restore_keeps_checkpoint_when_dependencies_match(self) -> None:
        from src.application.generate_story import GenerateStory
        from src.job_queue import PipelineContext
        from src.storage.checkpoint import CheckpointStore

        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "cp.db")
            outputs = _sample_outputs()
            bible = outputs["bible"]
            story = outputs["story"]
            store.save("world_builder", phase=1, seed=42, output=bible,
                       output_key="bible",
                       artifact_id=artifact_id("bible", bible),
                       depends_on={})
            store.save("story_writer", phase=3, seed=42, output=story,
                       output_key="story",
                       artifact_id=artifact_id("story", story),
                       depends_on={"bible": artifact_id("bible", bible)})

            ctx = PipelineContext(run_id="r", seed=42)
            GenerateStory._restore_checkpoints(ctx, store)
            assert ctx.outputs.get("bible") == bible
            assert ctx.outputs.get("story") == story
            # Nothing dropped
            assert store.load("story_writer") is not None

    def test_restore_drops_stale_downstream_when_upstream_changed(self) -> None:
        """Bible regenerated to a NEW artifact between runs; a story checkpoint
        that still references the OLD bible ID must be dropped."""
        from src.application.generate_story import GenerateStory
        from src.job_queue import PipelineContext
        from src.storage.checkpoint import CheckpointStore

        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "cp.db")
            outputs = _sample_outputs()
            old_bible = {"schema_version": 1, "world_name": "OLD", "seed": 42}
            new_bible = outputs["bible"]  # Different content → different ID
            story = outputs["story"]

            # world_builder checkpoint now holds the NEW bible...
            store.save("world_builder", phase=1, seed=42, output=new_bible,
                       output_key="bible",
                       artifact_id=artifact_id("bible", new_bible),
                       depends_on={})
            # ...but the story checkpoint was saved against the OLD bible
            store.save("story_writer", phase=3, seed=42, output=story,
                       output_key="story",
                       artifact_id=artifact_id("story", story),
                       depends_on={"bible": artifact_id("bible", old_bible)})

            ctx = PipelineContext(run_id="r", seed=42)
            GenerateStory._restore_checkpoints(ctx, store)

            # Bible restored; stale story checkpoint dropped + not restored
            assert ctx.outputs.get("bible") == new_bible
            assert store.load("story_writer") is None
            assert "story" not in ctx.outputs

    def test_restore_drops_downstream_when_upstream_missing(self) -> None:
        from src.application.generate_story import GenerateStory
        from src.job_queue import PipelineContext
        from src.storage.checkpoint import CheckpointStore

        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "cp.db")
            story = _sample_outputs()["story"]
            store.save("story_writer", phase=3, seed=42, output=story,
                       output_key="story",
                       depends_on={"bible": "world_a1b2c3d4"})
            ctx = PipelineContext(run_id="r", seed=42)
            GenerateStory._restore_checkpoints(ctx, store)
            assert store.load("story_writer") is None
            assert "story" not in ctx.outputs


# ── X5: PackageAcceptance provenance checks ──────────────────────────────


class TestPackageAcceptanceProvenance:
    """X5: the acceptance gate enforces provenance consistency."""

    def _valid_package(self, tmp_path: Path) -> Path:
        """Build a minimal acceptance-valid .story with provenance."""
        from tests.test_phase56q import _write_package
        pkg = tmp_path / "valid.story"
        _write_package(pkg, node_count=1, image_nodes={0}, midi_nodes={0})
        return pkg

    def test_valid_package_with_provenance_accepted(self, tmp_path: Path) -> None:
        from src.storage.package_acceptance import PackageAcceptance
        pkg = self._valid_package(tmp_path)
        result = PackageAcceptance().validate(pkg)
        assert result.accepted, result.format_issues()

    def test_missing_provenance_rejected(self, tmp_path: Path) -> None:
        from src.storage.package_acceptance import PackageAcceptance
        pkg = self._valid_package(tmp_path)
        # Strip the provenance section to simulate a legacy/stripped manifest
        with zipfile.ZipFile(pkg, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            manifest.pop("provenance", None)
            other = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            for name, data in other.items():
                zf.writestr(name, data)

        result = PackageAcceptance().validate(pkg)
        assert not result.accepted
        assert any("provenance" in i.message.lower() for i in result.issues)

    def test_tampered_content_detected_by_recomputed_id(self, tmp_path: Path) -> None:
        """X5.2: changing packaged content invalidates the inventory ID."""
        from src.storage.package_acceptance import PackageAcceptance
        pkg = self._valid_package(tmp_path)
        with zipfile.ZipFile(pkg, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            bible = json.loads(zf.read("content/bible.json"))
            other = {n: zf.read(n) for n in zf.namelist()
                     if n not in ("manifest.json", "content/bible.json")}
        # Tamper with bible content (but not the manifest inventory)
        bible["world_name"] = "Tampered"
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("content/bible.json", json.dumps(bible))
            for name, data in other.items():
                zf.writestr(name, data)

        result = PackageAcceptance().validate(pkg)
        assert not result.accepted
        assert any("provenance mismatch" in i.message.lower() for i in result.issues)

    def test_depends_on_unknown_id_rejected(self, tmp_path: Path) -> None:
        from src.storage.package_acceptance import PackageAcceptance
        pkg = self._valid_package(tmp_path)
        with zipfile.ZipFile(pkg, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            other = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
        manifest["provenance"]["depends_on"]["story"] = ["world_ffffffff"]
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            for name, data in other.items():
                zf.writestr(name, data)

        result = PackageAcceptance().validate(pkg)
        assert not result.accepted
        assert any("unknown artifact id" in i.message.lower() for i in result.issues)

    def test_missing_dependency_edge_rejected(self, tmp_path: Path) -> None:
        """X5.3b: a declared artifact missing required upstream edges fails."""
        from src.storage.package_acceptance import PackageAcceptance
        pkg = self._valid_package(tmp_path)
        with zipfile.ZipFile(pkg, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            other = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
        # story must depend on bible; blank it out
        manifest["provenance"]["depends_on"]["story"] = []
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            for name, data in other.items():
                zf.writestr(name, data)

        result = PackageAcceptance().validate(pkg)
        assert not result.accepted
        assert any("missing upstream" in i.message.lower() for i in result.issues)

    def test_spurious_dependency_edge_rejected(self, tmp_path: Path) -> None:
        """X5.3b: a root artifact (bible) declaring a spurious edge fails."""
        from src.storage.package_acceptance import PackageAcceptance
        pkg = self._valid_package(tmp_path)
        with zipfile.ZipFile(pkg, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            other = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
        # bible has no upstreams; declare a spurious edge to an ID that
        # DOES exist in the inventory (so only the edge check fires)
        story_id = manifest["provenance"]["inventory"]["story"]
        manifest["provenance"]["depends_on"]["bible"] = [story_id]
        with zipfile.ZipFile(pkg, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            for name, data in other.items():
                zf.writestr(name, data)

        result = PackageAcceptance().validate(pkg)
        assert not result.accepted
        assert any("unexpected upstream" in i.message.lower() for i in result.issues)


# ── end-to-end: ManifestBuilder emits provenance ─────────────────────────


class TestManifestBuilderProvenance:
    """ManifestBuilder emits a schema-valid, deterministic provenance."""

    @staticmethod
    def _context() -> Any:
        from src.job_queue import PipelineContext
        ctx = PipelineContext(run_id="x", seed=42)
        ctx.spec = type("S", (), {"title": "Provenance", "tone": "dark_fantasy",
                                  "temperature": 0.7})()
        for key, data in _sample_outputs().items():
            ctx.outputs[key] = data
        ctx.state["model_file_hashes"] = {"text_generator": "a" * 64}
        return ctx

    def test_manifest_has_provenance_section(self) -> None:
        import asyncio
        from src.storage.manifest_builder import ManifestBuilder
        out = asyncio.run(ManifestBuilder().run(self._context()))
        manifest: ManifestDict = out.data
        assert "provenance" in manifest
        prov = manifest["provenance"]
        assert set(prov["inventory"].keys()) == {
            "bible", "style_bible", "story", "graph", "images", "midi", "gm_index",
        }
        assert "depends_on" in prov
        assert "produced_by" in prov

    def test_manifest_provenance_validates_against_schema(self) -> None:
        import asyncio
        from pathlib import Path as _P
        from src.storage.manifest_builder import ManifestBuilder
        from src.validators.schema_validator import SchemaValidator

        schemas = str(_P(__file__).resolve().parent.parent / "schemas")
        if not _P(schemas).exists():
            pytest.skip("schemas not found")
        out = asyncio.run(ManifestBuilder(schemas_dir=schemas).run(self._context()))
        validator = SchemaValidator(schemas)
        result = validator.validate_manifest(out.data)
        assert result.is_valid, result.format_for_retry()

    def test_provenance_deterministic(self) -> None:
        import asyncio
        from src.storage.manifest_builder import ManifestBuilder
        out1 = asyncio.run(ManifestBuilder().run(self._context()))
        out2 = asyncio.run(ManifestBuilder().run(self._context()))
        assert out1.data["provenance"] == out2.data["provenance"]
