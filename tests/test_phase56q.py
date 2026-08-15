"""Tests for Phase 5.6 Q — Asset Coverage Policy.

Covers:
  Q1: Frozen v2 defaults require complete illustration and MIDI coverage.
  Q2: Production configuration rejects lower legacy thresholds.
  Q3: Package-v2 requires complete matching media sets before publication
      media counts in manifest stats.
  Q4: PackageAcceptance can still exercise legacy policy thresholds in isolated tests —
      below the minimum the package is REJECTED; at/above the minimum
      it is accepted but flagged incomplete.
  Q5: Legacy incomplete-but-accepted results remain distinguishable
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
    image_bytes: bytes | None = None,
    midi_bytes: bytes | None = None,
    thumb_bytes: bytes | None = None,
) -> None:
    """Write a minimal, acceptance-valid .story ZIP.

    When ``with_media_triggers`` is True every node carries an
    ``image_prompt`` and ``music_tone``; the ``image_nodes``/``midi_nodes``
    sets select which nodes actually have media files in the archive.
    content_hash is computed with the real canonical algorithm so
    acceptance's hash check passes.

    Phase 5.6 R: media defaults are structurally valid (512x512 PNG,
    non-zero MIDI); pass ``image_bytes``/``midi_bytes`` to exercise the
    binary acceptance checks.
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

    bible_dict = {"schema_version": 1, "world_name": "Q Test World"}
    story_dict = {"schema_version": 1, "chapters": []}
    gm_index_dict = {"schema_version": 1, "entries": []}
    style_bible_dict = {"schema_version": 1, "art_style": {}}
    artifacts: dict[str, bytes] = {
        "content/bible.json": json.dumps(bible_dict).encode(),
        "content/story.json": json.dumps(story_dict).encode(),
        "content/graph.json": json.dumps(graph).encode(),
        "content/gm_index.json": json.dumps(gm_index_dict).encode(),
        "content/style_bible.json": json.dumps(style_bible_dict).encode(),
    }
    # Phase 5.6 R: synthetic packages must contain structurally valid
    # media (correct size, non-zero MIDI duration) or acceptance rejects them.
    from src.storage.binary_checks import make_midi, make_png
    _IMG = image_bytes if image_bytes is not None else make_png(512, 512)
    _THUMB = thumb_bytes if thumb_bytes is not None else make_png(128, 128)
    _MIDI = midi_bytes if midi_bytes is not None else make_midi(ticks=96)
    for i in image_nodes:
        artifacts[f"content/images/node_{i:02d}.png"] = _IMG
        artifacts[f"content/thumbnails/node_{i:02d}.png"] = _THUMB
    for i in midi_nodes:
        artifacts[f"content/midi/node_{i:02d}.mid"] = _MIDI

    content_hash = compute_content_hash(artifacts)

    # Phase 5.6X: provenance — consistent inventory + dependency graph.
    from src.storage.provenance import build_provenance
    _models_used = {
        "text_generator": "mock", "validator": "mock",
        "image_generator": "mock", "music_generator": "mock",
    }
    _prompt_versions = {
        "world_builder": "v1", "story_writer": "v1", "game_designer": "v1",
        "art_director": "v1", "composer": "v1", "style_bible": "v1",
    }
    provenance = build_provenance(
        {
            "bible": bible_dict,
            "style_bible": style_bible_dict,
            "story": story_dict,
            "graph": graph,
            "images": {"images": {}, "image_count": len(image_nodes)},
            "midi": {"midi": {}, "midi_count": len(midi_nodes)},
            "gm_index": gm_index_dict,
        },
        _models_used,
        _prompt_versions,
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "story_id": "qtest-story-id-0001",
        "title": "Q Test",
        "tone": "dark_fantasy",
        "seed": 1,
        "generator_version": "0.1.0",
        "models_used": _models_used,
        "prompt_versions": _prompt_versions,
        "entry_point": "node_00",
        "provenance": provenance,
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
    """Q1/Q2: frozen v2 media policy requires complete coverage."""

    def test_defaults_require_complete_images_and_midi(self) -> None:
        from src.pipeline.policy import CoveragePolicy

        policy = CoveragePolicy.default()
        assert policy.image_min == 1.0
        assert policy.midi_min == 1.0

    def test_from_config_rejects_incomplete_values(self) -> None:
        from src.pipeline.policy import CoveragePolicy

        class Cfg:
            image_coverage = 0.9
            midi_coverage = 0.5

        with pytest.raises(ValueError, match="complete image and MIDI"):
            CoveragePolicy.from_config(Cfg())

    def test_from_config_rejects_out_of_range_values(self) -> None:
        from src.pipeline.policy import CoveragePolicy

        class Cfg:
            image_coverage = 1.5
            midi_coverage = -0.2

        with pytest.raises(ValueError, match="complete image and MIDI"):
            CoveragePolicy.from_config(Cfg())

    def test_from_config_missing_fields_use_defaults(self) -> None:
        """Q2: configs without coverage keys fall back to defaults."""
        from src.pipeline.policy import CoveragePolicy

        class Cfg:
            pass

        policy = CoveragePolicy.from_config(Cfg())
        assert policy.image_min == 1.0
        assert policy.midi_min == 1.0

    def test_yaml_rejects_incomplete_coverage(self, tmp_path: Path) -> None:
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

        with pytest.raises(ValueError, match="complete image and MIDI"):
            AppConfig.from_yaml(cfg_path)


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

    def _validate(self, package: Path) -> Any:
        from src.storage.package_acceptance import PackageAcceptance

        gate = PackageAcceptance(schemas_dir=None)
        return gate.validate(package)

    def test_full_coverage_accepted_and_complete(self, tmp_path: Path) -> None:
        """All nodes with media → accepted, complete, coverage 1.0/1.0."""
        pkg = tmp_path / "full.story"
        _write_package(pkg, node_count=2, image_nodes={0, 1}, midi_nodes={0, 1})

        result = self._validate(pkg)
        assert result.accepted, result.format_issues()
        assert result.complete is True
        assert result.coverage == {"images": 1.0, "midi": 1.0}

    def test_below_minimum_images_rejected(self, tmp_path: Path) -> None:
        """50% images with a 100% requirement → REJECTED."""
        pkg = tmp_path / "low_images.story"
        _write_package(pkg, node_count=2, image_nodes={0}, midi_nodes={0, 1})

        result = self._validate(pkg)
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

        result = self._validate(pkg)
        assert result.accepted is False, result.format_issues()
        assert result.coverage["midi"] == pytest.approx(0.5)
        assert any(
            "coverage" in i.message.lower() and i.severity == "error"
            for i in result.issues
        )

    def test_incomplete_media_is_never_accepted(self, tmp_path: Path) -> None:
        """Frozen v2 media completeness cannot be relaxed by a threshold."""
        pkg = tmp_path / "partial.story"
        _write_package(pkg, node_count=2, image_nodes={0}, midi_nodes={0, 1})

        result = self._validate(pkg)
        assert result.accepted is False
        assert result.complete is False
        assert result.coverage["images"] == pytest.approx(0.5)
        assert result.coverage["midi"] == pytest.approx(1.0)
        assert any(
            "mandatory 100%" in i.message.lower() and i.severity == "error"
            for i in result.issues
        ), f"Expected a mandatory-media error: {[i.message for i in result.issues]}"

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
