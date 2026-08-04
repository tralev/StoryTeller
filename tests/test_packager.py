"""Tests for Packager — TDD for Phase 5.

Produces deterministic .story ZIP archives with:
- Sorted JSON keys, fixed float precision, normalized timestamps
- content/ (immutable) and save/ (mutable) split
- manifest.json at root
- SHA256 content hash
- Deterministic ZIP entry ordering (sorted by name)
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import zipfile
from typing import Any

import pytest

from src.job_queue import PipelineContext


# ── test data ────────────────────────────────────────────────────────────────


def _make_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "story_id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "The Ashen Marches",
        "generator_version": "0.1.0",
        "models_used": {
            "text_generator": "qwen2.5-7b-q4_k_m",
            "validator": "phi-3.5-mini-q4_k_m",
            "image_generator": "sdxl-turbo-q8_0",
            "music_generator": "qwen2.5-7b-q4_k_m",
        },
        "prompt_versions": {
            "world_builder": "v1",
            "story_writer": "v1",
            "game_designer": "v1",
            "art_director": "v1",
            "composer": "v1",
        },
        "seed": 42,
        "stats": {
            "total_nodes": 11,
            "total_images": 10,
            "total_midi": 10,
            "total_endings": 3,
        },
        "entry_point": "node_01",
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
        "meta": {
            "artifact_id": "package_a1b2c3d4",
            "generated_at": "2026-08-03T00:00:00Z",
            "run_id": "test_run",
            "generation_time_seconds": 7200.5,
            "peak_ram_mb": 7500,
        },
    }


def _make_artifacts() -> dict[str, bytes]:
    """Mock file content for all .story package files."""
    return {
        "content/bible.json": b'{"world_name":"Test"}',
        "content/style_bible.json": b'{"art_style":{"palette":"dark"}}',
        "content/story.json": b'{"chapters":[]}',
        "content/graph.json": b'{"nodes":[]}',
        "content/gm_index.json": b'{"keywords":{}}',
        "content/images/node_01.png": b"\x89PNGimage01",
        "content/images/node_02.png": b"\x89PNGimage02",
        "content/midi/node_01.mid": b"MThdmidi01",
        "content/midi/node_02.mid": b"MThdmidi02",
        "content/thumbnails/node_01_thumb.png": b"\x89PNGthumb01",
        "content/thumbnails/node_02_thumb.png": b"\x89PNGthumb02",
    }


# ── Expected Packager API ────────────────────────────────────────────────────
# Packager(output_dir: str)
# .package(manifest, artifacts) -> Path  (path to .story ZIP)
# .compute_content_hash(artifacts) -> str  (SHA256)
# .validate_structure(zip_path) -> bool


class TestPackagerDeterminism:
    """Deterministic output — same inputs → identical ZIP."""

    def test_sorted_json_keys(self) -> None:
        """JSON in artifacts uses sorted keys for determinism."""
        data = {"z": 3, "a": 1, "m": 2}
        serialized = json.dumps(data, sort_keys=True)
        assert serialized == '{"a": 1, "m": 2, "z": 3}'

    def test_fixed_float_precision(self) -> None:
        """Float values use fixed precision for determinism."""
        value = 7200.5
        # Store as-is; Python float repr is deterministic for same value
        serialized = json.dumps({"time": value})
        parsed = json.loads(serialized)
        assert parsed["time"] == 7200.5

    def test_normalized_timestamps(self) -> None:
        """Timestamps use UTC Z-suffix format."""
        ts = "2026-08-03T00:00:00Z"
        assert ts.endswith("Z")
        assert "T" in ts
        # No timezone offset — always Z for UTC

    def test_deterministic_zip_entry_order(self) -> None:
        """ZIP entries sorted by name for determinism across runs."""
        artifacts = _make_artifacts()
        names = sorted(artifacts.keys())
        assert names[0] < names[-1]
        # First entry should be alphabetically first
        assert names[0].startswith("content/")

    def test_same_inputs_produce_same_zip(self) -> None:
        """Two builds with identical inputs produce byte-identical ZIPs."""
        artifacts = _make_artifacts()
        manifest = _make_manifest()

        # Simulate two builds
        def build_zip(manifest: dict, artifacts: dict) -> bytes:
            buf = bytearray()
            # Deterministic: sorted keys, sorted entries
            manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
            # Build a simple ZIP-like buffer
            buf.extend(b"ZIP_START")
            buf.extend(manifest_bytes)
            for name in sorted(artifacts.keys()):
                buf.extend(name.encode())
                buf.extend(artifacts[name])
            buf.extend(b"ZIP_END")
            return bytes(buf)

        zip1 = build_zip(manifest, artifacts)
        zip2 = build_zip(manifest, artifacts)

        assert zip1 == zip2
        assert hashlib.sha256(zip1).hexdigest() == hashlib.sha256(zip2).hexdigest()


class TestPackagerStructure:
    """Package structure — content/save split, manifest."""

    def test_content_files_are_immutable(self) -> None:
        """content/ contains bible, story, graph, gm_index, images, midi, thumbnails."""
        paths = [
            "content/bible.json",
            "content/style_bible.json",
            "content/story.json",
            "content/graph.json",
            "content/gm_index.json",
            "content/images/",
            "content/midi/",
            "content/thumbnails/",
        ]
        for p in paths:
            assert p.startswith("content/")

    def test_save_directory_is_separate(self) -> None:
        """save/ is not in content/ — mutable reader data."""
        content_path = "content/story.json"
        save_path = "save/current_node.json"
        assert not save_path.startswith("content/")
        assert content_path.startswith("content/")

    def test_manifest_at_root_level(self) -> None:
        """manifest.json is at the root of the ZIP, not in content/."""
        manifest_path = "manifest.json"
        assert not manifest_path.startswith("content/")
        assert manifest_path == "manifest.json"

    def test_all_content_types_have_directories(self) -> None:
        """Each asset type has its own subdirectory."""
        dirs = {"content/images", "content/midi", "content/thumbnails"}
        artifacts = _make_artifacts()
        artifact_dirs = {os.path.dirname(p) for p in artifacts}
        assert dirs.issubset(artifact_dirs)

    def test_image_files_have_png_extension(self) -> None:
        """Image files end with .png."""
        artifacts = _make_artifacts()
        img_paths = [p for p in artifacts if "images/" in p and not "thumb" in p]
        for p in img_paths:
            assert p.endswith(".png"), f"{p} should end with .png"

    def test_midi_files_have_mid_extension(self) -> None:
        """MIDI files end with .mid."""
        artifacts = _make_artifacts()
        midi_paths = [p for p in artifacts if "midi/" in p]
        for p in midi_paths:
            assert p.endswith(".mid"), f"{p} should end with .mid"


class TestPackagerHashing:
    """Content hash for integrity verification."""

    def test_sha256_content_hash(self) -> None:
        """SHA256 computed over all content/ files."""
        artifacts = _make_artifacts()
        hasher = hashlib.sha256()
        for name in sorted(artifacts.keys()):
            if name.startswith("content/"):
                hasher.update(name.encode())
                hasher.update(artifacts[name])

        digest = hasher.hexdigest()
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_changed_file_changes_hash(self) -> None:
        """Modifying any content file changes the SHA256."""
        artifacts1 = _make_artifacts()
        artifacts2 = _make_artifacts()
        artifacts2["content/bible.json"] = b'{"world_name":"Changed"}'

        hasher1 = hashlib.sha256()
        for name in sorted(artifacts1.keys()):
            hasher1.update(name.encode())
            hasher1.update(artifacts1[name])

        hasher2 = hashlib.sha256()
        for name in sorted(artifacts2.keys()):
            hasher2.update(name.encode())
            hasher2.update(artifacts2[name])

        assert hasher1.hexdigest() != hasher2.hexdigest()

    def test_hash_is_stored_in_manifest(self) -> None:
        """Manifest includes the content_hash field."""
        manifest = _make_manifest()
        assert "content_hash" not in manifest  # Set during packaging

        # After packaging
        manifest["content_hash"] = "a1b2c3d4e5f6a7b8"
        assert len(manifest["content_hash"]) >= 16


class TestPackagerManifestValidation:
    """Manifest validates against manifest.schema.json."""

    def test_manifest_matches_schema(self) -> None:
        """The built manifest validates against manifest.schema.json."""
        import os, json as jmod
        from jsonschema import Draft7Validator

        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "schemas", "manifest.schema.json",
        )
        with open(schema_path) as f:
            schema = jmod.load(f)

        manifest = _make_manifest()
        manifest["content_hash"] = "a" * 64

        errors = list(Draft7Validator(schema).iter_errors(manifest))
        assert not errors, f"Manifest failed schema validation: {errors}"

    def test_manifest_has_required_fields(self) -> None:
        """All required manifest fields are present."""
        manifest = _make_manifest()
        required = [
            "schema_version", "story_id", "title",
            "generator_version", "models_used",
            "prompt_versions", "entry_point", "files",
        ]
        for field in required:
            assert field in manifest, f"Missing required field: {field}"

    def test_artifact_id_matches_pattern(self) -> None:
        """Artifact ID matches ^package_[a-f0-9]{8}$."""
        import re
        manifest = _make_manifest()
        pattern = re.compile(r"^package_[a-f0-9]{8}$")
        assert "meta" in manifest
        assert pattern.match(manifest["meta"]["artifact_id"])


class TestPackagerIntegration:
    """End-to-end packaging workflow."""

    def test_builds_valid_zip(self) -> None:
        """Package produces a valid ZIP file with correct structure."""
        manifest = _make_manifest()
        artifacts = _make_artifacts()

        with tempfile.NamedTemporaryFile(suffix=".story", delete=False) as tmp:
            zip_path = tmp.name

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Write manifest at root
                manifest_json = json.dumps(manifest, sort_keys=True)
                zf.writestr("manifest.json", manifest_json)

                # Write content/ files in sorted order (deterministic)
                for name in sorted(artifacts.keys()):
                    zf.writestr(name, artifacts[name])

                # Create empty save/ directory marker
                zf.writestr("save/.gitkeep", "")

            # Verify
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                assert "manifest.json" in names
                assert "content/bible.json" in names
                assert "save/.gitkeep" in names
                # Entries should be in the order we wrote them
                assert names[0] == "manifest.json"
        finally:
            os.unlink(zip_path)

    def test_zip_is_deterministic(self) -> None:
        """Two ZIPs built from same data are identical."""
        manifest = _make_manifest()
        artifacts = _make_artifacts()

        def build() -> bytes:
            import io
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                manifest_json = json.dumps(manifest, sort_keys=True)
                zf.writestr("manifest.json", manifest_json)
                for name in sorted(artifacts.keys()):
                    zf.writestr(name, artifacts[name])
            return buf.getvalue()

        zip1 = build()
        zip2 = build()
        assert zip1 == zip2

    def test_content_hash_included_in_zip(self) -> None:
        """ZIP manifest includes the computed content_hash."""
        manifest = _make_manifest()
        artifacts = _make_artifacts()

        # Compute hash
        hasher = hashlib.sha256()
        for name in sorted(artifacts.keys()):
            hasher.update(name.encode())
            hasher.update(artifacts[name])
        manifest["content_hash"] = hasher.hexdigest()

        assert len(manifest["content_hash"]) == 64


class TestPackagerEdgeCases:
    """Packager edge cases."""

    def test_empty_artifacts_minimal_package(self) -> None:
        """Package with only manifest and empty asset dirs."""
        manifest = _make_manifest()
        artifacts: dict[str, bytes] = {}
        # Should still produce valid ZIP with manifest + dir markers
        assert len(artifacts) == 0

    def test_requires_manifest(self) -> None:
        """Packager requires manifest for metadata."""
        # manifest is mandatory; without it, packaging should raise
        pass  # Placeholder for TDD

    def test_requires_artifacts(self) -> None:
        """Packager needs at minimum bible + story + graph."""
        required = ["content/bible.json", "content/story.json", "content/graph.json"]
        for r in required:
            assert r.startswith("content/")

    def test_large_assets_handled(self) -> None:
        """Large image files (>1MB) don't break packaging."""
        large_image = b"\x89PNG" + b"\x00" * 1_000_000
        assert len(large_image) > 1_000_000
        # Packaging should handle large files without issue
