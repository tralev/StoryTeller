"""Test canonical .story v1 fixtures for cross-platform compatibility.

Phase 5.5K: Validates all fixture .story packages — valid ones pass
PackageAcceptance, invalid ones are rejected with appropriate errors.
These same fixtures are used by Android and iOS tests.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "story_packages"


def _read_fixture(name: str) -> Path:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture not found: {name} (run scripts/generate_story_fixtures.py)")
    return path


class TestValidFixtures:
    """Valid .story fixtures pass PackageAcceptance and have correct structure."""

    @pytest.mark.integration
    def test_minimal_valid_1_node_exists(self) -> None:
        """The minimal 1-node fixture is a valid ZIP file."""
        path = _read_fixture("minimal_valid_1_node.story")
        assert path.stat().st_size > 0

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "content/bible.json" in names
            assert "content/style_bible.json" in names
            assert "content/story.json" in names
            assert "content/graph.json" in names
            assert "content/gm_index.json" in names
            # Single node has image + MIDI
            assert "content/images/node_01.png" in names
            assert "content/midi/node_01.mid" in names
            assert "save/.gitkeep" in names

    @pytest.mark.integration
    def test_minimal_valid_1_node_passes_acceptance(self) -> None:
        """The minimal 1-node fixture passes PackageAcceptance."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("minimal_valid_1_node.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert result.accepted, f"Acceptance failed: {result.format_issues()}"

    @pytest.mark.integration
    def test_minimal_valid_has_correct_manifest(self) -> None:
        """Manifest fields match fixture contents."""
        path = _read_fixture("minimal_valid_1_node.story")
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))

        assert manifest["schema_version"] == 1
        assert manifest["title"] == "Minimal 1 Node"
        assert manifest["entry_point"] == "node_01"
        assert manifest["stats"]["total_nodes"] == 1
        assert manifest["files"]["bible"] == "content/bible.json"
        assert manifest["files"]["graph"] == "content/graph.json"

    @pytest.mark.integration
    def test_minimal_valid_graph_is_parseable(self) -> None:
        """Graph JSON is valid and entry_point exists."""
        path = _read_fixture("minimal_valid_1_node.story")
        with zipfile.ZipFile(path) as zf:
            graph = json.loads(zf.read("content/graph.json"))
            manifest = json.loads(zf.read("manifest.json"))

        node_ids = {n["node_id"] for n in graph["nodes"]}
        assert manifest["entry_point"] in node_ids, (
            f"entry_point {manifest['entry_point']} not in nodes: {node_ids}"
        )
        assert len(graph["nodes"]) == 1

    @pytest.mark.integration
    def test_complete_15_nodes_exists(self) -> None:
        """The complete 15-node fixture is valid with all assets."""
        path = _read_fixture("complete_15_nodes.story")
        assert path.stat().st_size > 0

        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "content/graph.json" in names

            graph = json.loads(zf.read("content/graph.json"))
            assert len(graph["nodes"]) == 15

            img_files = [n for n in names if n.startswith("content/images/")]
            midi_files = [n for n in names if n.startswith("content/midi/")]
            assert len(img_files) == 15, f"Expected 15 images, got {len(img_files)}"
            assert len(midi_files) == 15, f"Expected 15 MIDI tracks, got {len(midi_files)}"

    @pytest.mark.integration
    def test_complete_15_nodes_passes_acceptance(self) -> None:
        """The complete 15-node fixture passes PackageAcceptance."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("complete_15_nodes.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert result.accepted, f"Acceptance failed: {result.format_issues()}"


class TestInvalidFixtures:
    """Invalid .story fixtures are properly rejected."""

    @pytest.mark.integration
    def test_missing_manifest_rejected(self) -> None:
        """Fixture missing manifest.json fails acceptance."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("invalid_missing_manifest.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert not result.accepted, "Expected rejection, but fixture was accepted"
        assert any("manifest.json" in i.message or "manifest.json" in i.path
                   for i in result.issues), (
            f"Expected manifest-related error, got: {result.format_issues()}"
        )

    @pytest.mark.integration
    def test_bad_graph_ref_rejected(self) -> None:
        """Fixture with entry_point pointing to missing node fails acceptance."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("invalid_bad_graph_ref.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert not result.accepted, "Expected rejection, but fixture was accepted"
        assert any("node_nonexistent" in i.message or "entry" in i.message.lower()
                   for i in result.issues), (
            f"Expected entry-point error, got: {result.format_issues()}"
        )

    @pytest.mark.integration
    def test_path_traversal_rejected(self) -> None:
        """Fixture with ../ path traversal is rejected."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("invalid_path_traversal.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert not result.accepted, "Expected rejection, but fixture was accepted"
        assert any("path traversal" in i.message.lower() or "unsafe" in i.message.lower()
                   for i in result.issues), (
            f"Expected path traversal error, got: {result.format_issues()}"
        )

    @pytest.mark.integration
    def test_unsupported_version_rejected(self) -> None:
        """Fixture with schema_version=99 is REJECTED by acceptance (I7).

        A future package format must not be silently accepted and misread;
        versions above SUPPORTED_SCHEMA_VERSION are an error.
        """
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("invalid_unsupported_version.story")
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["schema_version"] == 99, "Fixture should have schema_version=99"

        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert not result.accepted, "Expected rejection, but fixture was accepted"
        assert any("schema_version" in i.message.lower() for i in result.issues), (
            f"Expected schema_version error, got: {result.format_issues()}"
        )

    @pytest.mark.integration
    def test_hash_mismatch_detectable(self) -> None:
        """Fixture with wrong content_hash can be detected."""
        path = _read_fixture("invalid_hash_mismatch.story")
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        # The hash is obviously wrong — any verifier should catch this
        assert manifest["content_hash"] == "deadbeef" * 8

    @pytest.mark.integration
    def test_corrupt_image_rejected(self) -> None:
        """R5: fixture with an undecodable PNG is rejected (R1)."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("invalid_corrupt_image.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert not result.accepted, "Expected rejection, but fixture was accepted"
        assert any("corrupt png" in i.message.lower() for i in result.issues), (
            f"Expected Corrupt PNG error, got: {result.format_issues()}"
        )

    @pytest.mark.integration
    def test_corrupt_midi_rejected(self) -> None:
        """R5: fixture with a zero-duration MIDI is rejected (R3/R4)."""
        from src.storage.package_acceptance import PackageAcceptance

        path = _read_fixture("invalid_corrupt_midi.story")
        gate = PackageAcceptance()
        result = gate.validate(str(path))
        assert not result.accepted, "Expected rejection, but fixture was accepted"
        assert any("invalid midi" in i.message.lower() for i in result.issues), (
            f"Expected Invalid MIDI error, got: {result.format_issues()}"
        )


class TestSchemaVersionBoundary:
    """I7: schema_version must be an int within [1, SUPPORTED_SCHEMA_VERSION].

    Locks the exact acceptance interval — both too-old (< 1) and too-new
    (> SUPPORTED_SCHEMA_VERSION) manifests are rejected, as are non-int
    values. Previously only the lower bound was enforced, so a future
    package format (e.g. schema_version=99) would be silently accepted.
    """

    @staticmethod
    def _check(manifest: dict[str, Any]) -> list[Any]:
        from src.storage.package_acceptance import PackageAcceptance

        return PackageAcceptance._check_supported_versions(manifest)

    def test_supported_version_accepted(self) -> None:
        """schema_version == SUPPORTED_SCHEMA_VERSION produces no issues."""
        from src.storage.package_acceptance import PackageAcceptance

        issues = self._check({"schema_version": PackageAcceptance.SUPPORTED_SCHEMA_VERSION})
        assert issues == [], f"Expected no issues, got: {issues}"

    def test_version_above_supported_rejected(self) -> None:
        """Upper bound: schema_version = SUPPORTED + 1 is rejected."""
        from src.storage.package_acceptance import PackageAcceptance

        issues = self._check({"schema_version": PackageAcceptance.SUPPORTED_SCHEMA_VERSION + 1})
        assert issues, "Expected rejection for version above supported"
        assert issues[0].severity == "error"
        assert "schema_version" in issues[0].message.lower()
        assert "1.." in issues[0].message, f"Message should name the supported range: {issues[0].message}"

    def test_version_below_one_rejected(self) -> None:
        """Lower bound: schema_version = 0 is rejected."""
        issues = self._check({"schema_version": 0})
        assert issues, "Expected rejection for version 0"
        assert issues[0].severity == "error"

    def test_negative_version_rejected(self) -> None:
        """Negative schema_version is rejected."""
        issues = self._check({"schema_version": -1})
        assert issues, "Expected rejection for negative version"
        assert issues[0].severity == "error"

    def test_non_int_version_rejected(self) -> None:
        """Non-integer schema_version (e.g. a float or string) is rejected."""
        for bad in ["1", 1.0, True, None]:
            issues = self._check({"schema_version": bad})
            assert issues, f"Expected rejection for schema_version={bad!r}"
            assert issues[0].severity == "error"

    def test_missing_version_rejected(self) -> None:
        """Missing schema_version is rejected."""
        issues = self._check({})
        assert issues, "Expected rejection for missing schema_version"
        assert "Missing schema_version" in issues[0].message


class TestFixtureCrossPlatform:
    """Tests that apply to ANY .story consumer (Python, Android, iOS)."""

    @pytest.mark.integration
    @pytest.mark.parametrize("fixture_name", [
        "minimal_valid_1_node.story",
        "complete_15_nodes.story",
    ])
    def test_valid_fixture_is_well_formed_zip(self, fixture_name: str) -> None:
        """Every valid fixture is a readable ZIP with no corruption."""
        path = _read_fixture(fixture_name)
        with zipfile.ZipFile(path) as zf:
            assert zf.testzip() is None, f"Corrupt ZIP entry: {zf.testzip()}"

    @pytest.mark.integration
    @pytest.mark.parametrize("fixture_name", [
        "minimal_valid_1_node.story",
        "complete_15_nodes.story",
    ])
    def test_valid_fixture_has_immutable_mutable_split(self, fixture_name: str) -> None:
        """Every valid fixture has content/ (immutable) and save/ (mutable)."""
        path = _read_fixture(fixture_name)
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            content_files = [n for n in names if n.startswith("content/") and not n.endswith("/")]
            save_files = [n for n in names if n.startswith("save/")]
            assert len(content_files) >= 3, f"Expected >=3 content files, got {len(content_files)}"
            assert len(save_files) >= 1, f"Expected >=1 save file, got {len(save_files)}"

    @pytest.mark.integration
    @pytest.mark.parametrize("fixture_name", [
        "minimal_valid_1_node.story",
        "complete_15_nodes.story",
    ])
    def test_valid_fixture_all_json_parseable(self, fixture_name: str) -> None:
        """Every JSON file in the fixture is valid parseable JSON."""
        path = _read_fixture(fixture_name)
        with zipfile.ZipFile(path) as zf:
            for entry in zf.namelist():
                if entry.endswith(".json"):
                    content = json.loads(zf.read(entry))
                    assert content is not None, f"Null content in {entry}"

    @pytest.mark.integration
    def test_valid_fixture_graph_references_are_consistent(self) -> None:
        """All choice target_node values exist as real nodes (both fixtures)."""
        for name in ["minimal_valid_1_node.story", "complete_15_nodes.story"]:
            path = _read_fixture(name)
            with zipfile.ZipFile(path) as zf:
                graph = json.loads(zf.read("content/graph.json"))
                node_ids = {n["node_id"] for n in graph["nodes"]}
                for node in graph["nodes"]:
                    for choice in node.get("choices", []):
                        target = choice["target_node"]
                        assert target in node_ids, (
                            f"[{name}] target_node '{target}' referenced from "
                            f"'{node['node_id']}' does not exist"
                        )
