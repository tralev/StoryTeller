"""Tests for Phase 5.6 R — Binary Asset Acceptance.

Covers:
  R1: Decode every packaged PNG and reject corrupt images.
  R2: Verify full images and thumbnails have the configured dimensions.
  R3: Parse every MIDI and reject corrupt/empty tracks.
  R4: Verify MIDI duration is greater than zero.
  R5: Corrupt PNG and MIDI archive fixtures (fixture-level tests live in
      test_story_fixtures.py; here we test the validators + acceptance).

The validators in ``src/storage/binary_checks`` are pure-stdlib — no
Pillow/music21 dependency in the acceptance gate.
"""

from __future__ import annotations

import json
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest

from src.storage.binary_checks import (
    make_midi,
    make_png,
    validate_midi,
    validate_png,
)

from .test_phase56q import _write_package


# ── R1/R2: PNG validator + builder ─────────────────────────────────────────


class TestPngValidation:
    """R1: structural decode of PNG bytes; R2: dimensions reported."""

    def test_valid_png_reports_dimensions(self) -> None:
        png = make_png(512, 512)
        check = validate_png(png)
        assert check.ok, check.error
        assert check.size == (512, 512)

    def test_thumbnail_size_reported(self) -> None:
        check = validate_png(make_png(128, 128))
        assert check.ok, check.error
        assert check.size == (128, 128)

    def test_invalid_signature_rejected(self) -> None:
        check = validate_png(b"GIF89a-not-a-png")
        assert not check.ok
        assert "signature" in check.error.lower()

    def test_truncated_png_rejected(self) -> None:
        """R1: cutting the stream (no IEND) must be detected."""
        png = make_png(512, 512)
        check = validate_png(png[: len(png) - 10])
        assert not check.ok
        assert "iend" in check.error.lower() or "truncat" in check.error.lower()

    def test_corrupted_idat_crc_rejected(self) -> None:
        """R1: a flipped byte in IDAT fails the chunk CRC check."""
        png = bytearray(make_png(512, 512))
        # Flip a byte inside the IDAT chunk data (after the chunk header).
        idat_pos = png.find(b"IDAT")
        png[idat_pos + 20] ^= 0xFF
        check = validate_png(bytes(png))
        assert not check.ok
        assert "crc" in check.error.lower()

    def test_invalid_idat_with_valid_crc_rejected(self) -> None:
        """A valid chunk CRC cannot substitute for actually decoding pixels."""
        png = bytearray(make_png(16, 16))
        type_pos = png.find(b"IDAT")
        length_pos = type_pos - 4
        data_pos = type_pos + 4
        chunk_len = struct.unpack(">I", png[length_pos:type_pos])[0]
        png[data_pos:data_pos + chunk_len] = b"x" * chunk_len
        crc = zlib.crc32(b"IDAT" + png[data_pos:data_pos + chunk_len]) & 0xFFFFFFFF
        png[data_pos + chunk_len:data_pos + chunk_len + 4] = struct.pack(">I", crc)
        check = validate_png(bytes(png))
        assert not check.ok
        assert "idat" in check.error.lower()

    def test_missing_iend_rejected(self) -> None:
        png = bytearray(make_png(16, 16))
        # Drop the final IEND chunk (last 12 bytes).
        check = validate_png(bytes(png[:-12]))
        assert not check.ok

    def test_builders_roundtrip_different_sizes(self) -> None:
        for w, h in [(512, 512), (128, 128), (64, 64)]:
            check = validate_png(make_png(w, h))
            assert check.ok, check.error
            assert check.size == (w, h)


# ── R3/R4: MIDI validator + builder ────────────────────────────────────────


class TestMidiValidation:
    """R3: parse MIDI + reject empty tracks; R4: duration > 0."""

    def test_valid_midi_has_positive_duration(self) -> None:
        midi = make_midi(ticks=96)
        check = validate_midi(midi)
        assert check.ok, check.error
        assert check.duration_s > 0
        assert check.tracks >= 1

    def test_missing_header_rejected(self) -> None:
        check = validate_midi(b"RIFF0000garbage")
        assert not check.ok
        assert "MThd" in check.error

    def test_empty_track_rejected(self) -> None:
        """R3: a track with only the end-of-track marker is empty."""
        midi = (
            b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x80"
            b"MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
        )
        check = validate_midi(midi)
        assert not check.ok
        assert "empty" in check.error.lower()

    def test_zero_duration_rejected(self) -> None:
        """R4: only meta events, no delta time → duration is zero."""
        # Tempo meta event only (delta 0), then end-of-track.
        track = b"\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00"
        midi = (
            b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x80"
            + b"MTrk" + (len(track)).to_bytes(4, "big") + track
        )
        check = validate_midi(midi)
        assert not check.ok
        assert "zero" in check.error.lower()

    def test_truncated_track_rejected(self) -> None:
        """R3: MTrk chunk length exceeding the buffer is corruption."""
        midi = (
            b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x80"
            b"MTrk\x00\x00\x00\xff\xff\x00"
        )
        check = validate_midi(midi)
        assert not check.ok

    def test_no_tracks_rejected(self) -> None:
        midi = b"MThd\x00\x00\x00\x06\x00\x00\x00\x00\x00\x80"
        check = validate_midi(midi)
        assert not check.ok
        assert "mtrk" in check.error.lower()

    def test_declared_track_count_mismatch_rejected(self) -> None:
        midi = bytearray(make_midi())
        midi[10:12] = (2).to_bytes(2, "big")
        check = validate_midi(bytes(midi))
        assert not check.ok
        assert "track count" in check.error.lower()

    def test_missing_end_of_track_rejected(self) -> None:
        midi = bytearray(make_midi())
        del midi[-4:]
        track_length = int.from_bytes(midi[18:22], "big") - 4
        midi[18:22] = track_length.to_bytes(4, "big")
        check = validate_midi(bytes(midi))
        assert not check.ok
        assert "end-of-track" in check.error.lower()


class TestZipEntrySecurity:
    """Archive identity and path checks run before any content is trusted."""

    def test_duplicate_entry_rejected(self) -> None:
        infos = [zipfile.ZipInfo("manifest.json"), zipfile.ZipInfo("manifest.json")]
        from src.storage.package_acceptance import PackageAcceptance
        issues = PackageAcceptance._check_zip_entries(infos)
        assert any("duplicate" in issue.message.lower() for issue in issues)

    @pytest.mark.parametrize(
        "name", ["../escape", "/absolute", "C:/absolute", "dir\\escape", "a/./b"],
    )
    def test_unsafe_portable_path_rejected(self, name: str) -> None:
        from src.storage.package_acceptance import PackageAcceptance
        issues = PackageAcceptance._check_zip_entries([zipfile.ZipInfo(name)])
        assert any("unsafe" in issue.message.lower() for issue in issues)

    def test_case_collision_rejected(self) -> None:
        from src.storage.package_acceptance import PackageAcceptance
        infos = [zipfile.ZipInfo("content/A.json"), zipfile.ZipInfo("content/a.json")]
        issues = PackageAcceptance._check_zip_entries(infos)
        assert any("collides" in issue.message.lower() for issue in issues)


# ── R1-R4: acceptance integration on synthetic packages ────────────────────


class TestPackageBinaryAcceptance:
    """The acceptance gate rejects corrupt/mis-sized/mute media."""

    def _validate(self, pkg: Path) -> Any:
        from src.storage.package_acceptance import PackageAcceptance

        return PackageAcceptance(schemas_dir=None).validate(pkg)

    def test_valid_media_accepted(self, tmp_path: Path) -> None:
        pkg = tmp_path / "ok.story"
        _write_package(pkg, node_count=2, image_nodes={0, 1}, midi_nodes={0, 1})
        result = self._validate(pkg)
        assert result.accepted, result.format_issues()

    def test_corrupt_png_rejected(self, tmp_path: Path) -> None:
        """R1: a package whose PNG is not decodable is rejected."""
        pkg = tmp_path / "bad_png.story"
        _write_package(
            pkg, node_count=1, image_nodes={0}, midi_nodes={0},
            image_bytes=b"\x89PNG-not-a-real-image",
        )
        result = self._validate(pkg)
        assert not result.accepted
        assert any(
            "corrupt png" in i.message.lower()
            for i in result.issues
        ), f"Expected Corrupt PNG error: {result.format_issues()}"

    def test_wrong_dimensions_rejected(self, tmp_path: Path) -> None:
        """R2: a 64x64 image where 512x512 is configured is rejected."""
        pkg = tmp_path / "small_png.story"
        _write_package(
            pkg, node_count=1, image_nodes={0}, midi_nodes={0},
            image_bytes=make_png(64, 64),
        )
        result = self._validate(pkg)
        assert not result.accepted
        assert any(
            "dimensions" in i.message.lower()
            for i in result.issues
        ), f"Expected dimension error: {result.format_issues()}"

    def test_wrong_thumbnail_dimensions_rejected(self, tmp_path: Path) -> None:
        """R2: thumbnails are verified against thumb_size (128x128).

        Full image is a valid 512x512; only the thumbnail is the wrong
        size — the ``content/thumbnails/`` branch must reject it.
        """
        pkg = tmp_path / "small_thumb.story"
        _write_package(
            pkg, node_count=1, image_nodes={0}, midi_nodes={0},
            thumb_bytes=make_png(64, 64),
        )
        result = self._validate(pkg)
        assert not result.accepted
        thumb_issues = [
            i for i in result.issues
            if "thumbnails" in i.path and "dimensions" in i.message.lower()
        ]
        assert thumb_issues, (
            f"Expected a thumbnail dimension error, got: {result.format_issues()}"
        )
        assert any(
            "64x64" in i.message for i in thumb_issues
        ), f"Unexpected thumbnail issue: {[i.message for i in thumb_issues]}"

    def test_corrupt_midi_rejected(self, tmp_path: Path) -> None:
        """R3: a package with an unparseable MIDI is rejected."""
        pkg = tmp_path / "bad_midi.story"
        _write_package(
            pkg, node_count=1, image_nodes={0}, midi_nodes={0},
            midi_bytes=b"MThd\x00\x00\x00\x06broken",
        )
        result = self._validate(pkg)
        assert not result.accepted
        assert any(
            "invalid midi" in i.message.lower()
            for i in result.issues
        ), f"Expected Invalid MIDI error: {result.format_issues()}"

    def test_zero_duration_midi_rejected(self, tmp_path: Path) -> None:
        """R4: a structurally valid but silent MIDI is rejected."""
        empty = (
            b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x80"
            b"MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
        )
        pkg = tmp_path / "silent_midi.story"
        _write_package(
            pkg, node_count=1, image_nodes={0}, midi_nodes={0},
            midi_bytes=empty,
        )
        result = self._validate(pkg)
        assert not result.accepted
        assert any(
            "invalid midi" in i.message.lower()
            for i in result.issues
        ), f"Expected Invalid MIDI error: {result.format_issues()}"
