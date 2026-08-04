"""Tests for Phase 5.6 Q — Asset Coverage Policy.

Covers:
  Q1: Define whether illustrations and MIDI are required, optional,
      or threshold-based (CoveragePolicy defaults).
  Q2: Configurable minimum coverage from PipelineConfig (with clamping).
  Q3: ManifestBuilder records expected/completed/quarantined/missing
      media counts in manifest stats.
  Q4: PackageAcceptance enforces the configured coverage policy —
      below the minimum the package is REJECTED; at/above the minimum
      it is accepted but flagged incomplete.
  Q5: Incomplete-but-accepted packages are reported distinctly
      (AcceptanceResult.complete / .coverage, GenerationResult fields
      via the production-wiring quarantine test).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest


# ── synthetic .story package builder ────────────────────────────────────────


def _write_package(
    path: Path,
    node_count: int,
    image_nodes: set[int],
    midi_nodes: set[int],
    *,
    with_media_triggers: bool = True,
) -> None:
    """Write a minimal, acceptance-valid .story ZIP.

    When ``with_media_triggers`` is True every node carries an
    ``image_prompt`` and ``music_tone``; the ``image_nodes``/``midi_nodes``
    sets select which nodes actually have media files in the archive.
    content_hash is computed with the real canonical algorithm so
    acceptance's hash check passes.
    """
    from src.storage.content_hash import compute_content_hash

    nodes: list[dict[str, Any]] = []
    for i in range(node_count):
        node: dict[str, Any] = {
            "node_id": f"node_{i:02d}",
            "chapter": 1,
            "scene_type": "exploration",
            "description": f"Node {i}",
            "present_characters": [],
            "present_location": "loc_01",
            "present_creatures": [],
            "mood": "neutral",
            "choices": [],
            "endings": {"is_ending": False},
        }
        if with_media_triggers:
            node["image_prompt"] = f"illustration for node {i}"
            node["music_tone"] = f"tone {i}"
        nodes.append(node)
    graph = {
        "schema_version": 1,
        "starting_node": "node_00",
        "nodes": nodes,
        "endings_summary": [],
    }

    artifacts: dict[str, bytes] = {
        "content/bible.json": json.dumps(
            {"schema_version": 1, "world_name": "Q Test World"},
        ).encode(),
        "content/story.json": json.dumps(
            {"schema_version": 1, "chapters": []},
        ).encode(),
        "content/graph.json": json.dumps(graph).encode(),
        "content/gm_index.json": json.dumps(
            {"schema_version": 1, "entries": []},
        ).encode(),
        "content/style_bible.json": json.dumps(
            {"schema_version": 1, "art_style": {}},
        ).encode(),
    }
    for i in image_nodes:
        artifacts[f"content/images/node_{i:02d}.png"] = b"\x89PNG-fake-bytes"
    for i in midi_nodes:
        artifacts[f"content/midi/node_{i:02d}.mid"] = b"MThd-fake-bytes"

    content_hash = compute_content_hash(artifacts)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "story_id": "qtest-story-id-0001",
        "title": "Q Test",
        "tone": "dark_fantasy",
        "seed": 1,
        "generator_version": "0.1.0",
        "models_used": {},
        "prompt_versions": {},
        "entry_point": "node_00",
        "files": {
            "bible": "content/bible.json",
            "style_bible": "content/style_bible.json",
            "story": "content/story.json",
            "graph": "content/graph.json",
            "gm_index": "content/gm_index.json",
            "images": "content/images/",
            "midi": "content/midi/",
            "thumbnails": "content/thumbnails/",
        },
        "stats": {},
        "content_hash": content_hash,
        "meta": {
            "artifact_id": "pkg_qtest_0001",
            "generated_at": "2026-01-01T00:00:00Z",
        },
    }
    artifacts["manifest.json"] = json.dumps(manifest).encode()

    with zipfile.ZipFile(path, "w") as zf:
        for name, data in artifacts.items():
            zf.writestr(name, data)


# ── Q1/Q2: CoveragePolicy ──────────────────────────────────────────────────


class TestCoveragePolicy:
    """Q1/Q2: media type policy — required vs threshold, configurable."""

    def test_defaults_images_required_midi_threshold(self) -> None:
        """Q1: illustrations REQUIRED (1.0), MIDI threshold-based (0.8)."""
        from src.pipeline.policy import CoveragePolicy

        policy = CoveragePolicy.default()
        assert policy.image_min == 1.0
        assert policy.midi_min == 0.8

    def test_from_config_custom_values(self) -> None:
        """Q2: custom minima are read from the pipeline config."""
        from src.pipeline.policy import CoveragePolicy

        class Cfg:
            image_coverage = 0.9
            midi_coverage = 0.5

        policy = CoveragePolicy.from_config(Cfg())
        assert policy.image_min == 0.9
        assert policy.midi_min == 0.5

    def test_from_config_clamps_to_unit_interval(self) -> None:
        """Q2: out-of-range values clamp to [0.0, 1.0]."""
        from src.pipeline.policy import CoveragePolicy

        class Cfg:
            image_coverage = 1.5
            midi_coverage = -0.2

        policy = CoveragePolicy.from_config(Cfg())
        assert policy.image_min == 1.0
        assert policy.midi_min == 0.0

    def test_from_config_missing_fields_use_defaults(self) -> None:
        """Q2: configs without coverage keys fall back to defaults."""
        from src.pipeline.policy import CoveragePolicy

        class Cfg:
            pass

        policy = CoveragePolicy.from_config(Cfg())
        assert policy.image_min == 1.0
        assert policy.midi_min == 0.8

    def test_yaml_parses_coverage(self, tmp_path: Path) -> None:
        """Q2: models.yaml pipeline section feeds PipelineConfig fields."""
        import yaml

        from src.config import AppConfig

        cfg_path = tmp_path / "models.yaml"
        cfg_path.write_text(yaml.safe_dump({
            "generators": {
                "text": {"provider": "llama_cpp", "model": "m",
                         "quantization": "Q4_K_M"},
                "validator": {"provider": "llama_cpp", "model": "m",
                              "quantization": "Q4_K_M"},
                "image": {"provider": "sdcpp", "model": "m",
                          "quantization": "Q8_0"},
                "music": {"provider": "abc-notation", "model": "via-text",
                          "uses": "text"},
                "game_master": {"provider": "llama_cpp", "model": "m",
                                "quantization": "Q4_K_M"},
            },
            "pipeline": {"image_coverage": 0.9, "midi_coverage": 0.6},
        }))

        cfg = AppConfig.from_yaml(cfg_path)
        assert cfg.pipeline.image_coverage == 0.9
        assert cfg.pipeline.midi_coverage == 0.6


# ── Q3: manifest coverage stats ────────────────────────────────────────────


class TestManifestCoverageStats:
    """Q3: manifest stats record expected vs completed vs missing media."""

    @pytest.mark.asyncio
    async def test_stats_report_quarantined_and_missing(self) -> None:
        """Quarantined/missing counts are explicit in manifest stats.

        Graph: 3 nodes — 2 with image_prompt, 3 with music_tone.
        Images: 1 completed + 1 quarantined → missing_images = 1.
        MIDI:   2 completed, 0 quarantined → missing_midi = 1.
        """
        from src.job_queue import PipelineContext
        from src.storage.manifest_builder import ManifestBuilder

        ctx = PipelineContext(run_id="run_q3", seed=1)
        ctx.outputs["bible"] = {"world_name": "Q3 World"}
        ctx.outputs["graph"] = {
            "schema_version": 1,
            "starting_node": "node_00",
            "nodes": [
                {"node_id": "node_00", "image_prompt": "a", "music_tone": "t0"},
                {"node_id": "node_01", "music_tone": "t1"},
                {"node_id": "node_02", "image_prompt": "b", "music_tone": "t2"},
            ],
            "endings_summary": [],
        }
        ctx.outputs["images"] = {
            "images": {"node_00": {"ok": True}},
            "image_count": 1,
            "quarantined": 1,
            "total_bytes": 0,
            "skipped": 0,
        }
        ctx.outputs["midi"] = {
            "midi": {"node_00": {"ok": True}, "node_01": {"ok": True}},
            "midi_count": 2,
            "quarantined": 0,
            "total_bytes": 0,
            "skipped": 0,
        }

        out = await ManifestBuilder().run(ctx)
        stats = out.data["stats"]

        assert stats["nodes_with_image_prompt"] == 2
        assert stats["nodes_with_music_tone"] == 3
        assert stats["total_images"] == 1
        assert stats["total_midi"] == 2
        assert stats["quarantined_images"] == 1
        assert stats["quarantined_midi"] == 0
        assert stats["missing_images"] == 1  # 2 expected − 1 completed
        assert stats["missing_midi"] == 1    # 3 expected − 2 completed

    @pytest.mark.asyncio
    async def test_stats_zero_when_no_media(self) -> None:
        """Empty media sections produce zeroed coverage stats."""
        from src.job_queue import PipelineContext
        from src.storage.manifest_builder import ManifestBuilder

        ctx = PipelineContext(run_id="run_q3b", seed=1)
        ctx.outputs["bible"] = {"world_name": "Q3 World"}
        ctx.outputs["graph"] = {
            "schema_version": 1,
            "starting_node": "node_00",
            "nodes": [{"node_id": "node_00"}],
            "endings_summary": [],
        }

        out = await ManifestBuilder().run(ctx)
        stats = out.data["stats"]
        assert stats["nodes_with_image_prompt"] == 0
        assert stats["nodes_with_music_tone"] == 0
        assert stats["quarantined_images"] == 0
        assert stats["quarantined_midi"] == 0
        assert stats["missing_images"] == 0
        assert stats["missing_midi"] == 0


# ── Q2/Q5: CLI surfaces the coverage policy ────────────────────────────────


class TestCliCoverageReporting:
    """Q2/Q5: `forge config` reports the configured coverage minima."""

    def test_config_output_includes_coverage_keys(self) -> None:
        """The config command prints image/midi coverage minima."""
        import os
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "src", "config"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
            env={**os.environ, "PYTHONPATH": "src"},
        )
        assert result.returncode == 0, (
            f"config failed: {result.stderr}"
        )
        assert "image_coverage:" in result.stdout, (
            f"config output missing image_coverage:\n{result.stdout}"
        )
        assert "midi_coverage:" in result.stdout, (
            f"config output missing midi_coverage:\n{result.stdout}"
        )


# ── Q4: PackageAcceptance enforcement ──────────────────────────────────────


class TestPackageAcceptanceCoverage:
    """Q4: the coverage policy is enforced during acceptance."""

    def _validate(
        self, package: Path, image_min: float, midi_min: float,
    ) -> Any:
        from src.pipeline.policy import CoveragePolicy
        from src.storage.package_acceptance import PackageAcceptance

        gate = PackageAcceptance(
            schemas_dir=None,
            coverage=CoveragePolicy(image_min=image_min, midi_min=midi_min),
        )
        return gate.validate(package)

    def test_full_coverage_accepted_and_complete(self, tmp_path: Path) -> None:
        """All nodes with media → accepted, complete, coverage 1.0/1.0."""
        pkg = tmp_path / "full.story"
        _write_package(pkg, node_count=2, image_nodes={0, 1}, midi_nodes={0, 1})

        result = self._validate(pkg, image_min=1.0, midi_min=0.8)
        assert result.accepted, result.format_issues()
        assert result.complete is True
        assert result.coverage == {"images": 1.0, "midi": 1.0}

    def test_below_minimum_images_rejected(self, tmp_path: Path) -> None:
        """50% images with a 100% requirement → REJECTED."""
        pkg = tmp_path / "low_images.story"
        _write_package(pkg, node_count=2, image_nodes={0}, midi_nodes={0, 1})

        result = self._validate(pkg, image_min=1.0, midi_min=0.0)
        assert result.accepted is False, result.format_issues()
        assert result.coverage["images"] == pytest.approx(0.5)
        assert result.complete is False
        assert any(
            "coverage" in i.message.lower() and i.severity == "error"
            for i in result.issues
        ), f"Expected a coverage ERROR issue: {[i.message for i in result.issues]}"

    def test_below_minimum_midi_rejected(self, tmp_path: Path) -> None:
        """50% MIDI with a 100% requirement → REJECTED."""
        pkg = tmp_path / "low_midi.story"
        _write_package(pkg, node_count=2, image_nodes={0, 1}, midi_nodes={0})

        result = self._validate(pkg, image_min=0.0, midi_min=1.0)
        assert result.accepted is False, result.format_issues()
        assert result.coverage["midi"] == pytest.approx(0.5)
        assert any(
            "coverage" in i.message.lower() and i.severity == "error"
            for i in result.issues
        )

    def test_incomplete_but_accepted(self, tmp_path: Path) -> None:
        """Q5: 50% images ≥ 40% minimum → accepted, flagged incomplete."""
        pkg = tmp_path / "partial.story"
        _write_package(pkg, node_count=2, image_nodes={0}, midi_nodes={0, 1})

        result = self._validate(pkg, image_min=0.4, midi_min=0.0)
        assert result.accepted is True, result.format_issues()
        assert result.complete is False
        assert result.coverage["images"] == pytest.approx(0.5)
        assert result.coverage["midi"] == pytest.approx(1.0)
        # A warning (not error) flags the incomplete media
        assert any(
            "incomplete" in i.message.lower() and i.severity == "warning"
            for i in result.issues
        ), f"Expected an incomplete-media warning: {[i.message for i in result.issues]}"

    def test_default_policy_rejects_missing_images(self, tmp_path: Path) -> None:
        """Default policy (images required at 100%) rejects partial media."""
        from src.storage.package_acceptance import PackageAcceptance

        pkg = tmp_path / "default_policy.story"
        _write_package(pkg, node_count=2, image_nodes={0}, midi_nodes={0, 1})

        gate = PackageAcceptance(schemas_dir=None)  # coverage=None → default
        result = gate.validate(pkg)
        assert result.accepted is False, result.format_issues()
        assert result.coverage["images"] == pytest.approx(0.5)

    def test_no_expected_media_is_complete(self, tmp_path: Path) -> None:
        """A package with zero expected media is trivially complete."""
        from src.pipeline.policy import CoveragePolicy
        from src.storage.package_acceptance import PackageAcceptance

        pkg = tmp_path / "no_media.story"
        _write_package(
            pkg, node_count=2, image_nodes=set(), midi_nodes=set(),
            with_media_triggers=False,
        )

        gate = PackageAcceptance(
            schemas_dir=None, coverage=CoveragePolicy(image_min=1.0, midi_min=1.0),
        )
        result = gate.validate(pkg)
        assert result.accepted is True, result.format_issues()
        assert result.complete is True
        # Zero expected media → every ratio trivially 1.0 (complete).
        assert result.coverage == {"images": 1.0, "midi": 1.0}
