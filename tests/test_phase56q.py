"""Phase 5.6Q coverage policy on the frozen v2 package contract."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from src.pipeline.policy import CoveragePolicy
from src.storage.package_v2 import validate_v2_package

FIXTURES = Path(__file__).parent / "fixtures" / "v2"


def test_defaults_require_complete_images_and_midi() -> None:
    policy = CoveragePolicy.default()
    assert policy.image_min == 1.0
    assert policy.midi_min == 1.0


@pytest.mark.parametrize(("images", "midi"), [(0.9, 1.0), (1.0, 0.5), (1.5, -0.2)])
def test_config_rejects_incomplete_or_out_of_range_values(images: float, midi: float) -> None:
    class Config:
        image_coverage = images
        midi_coverage = midi

    with pytest.raises(ValueError, match="complete image and MIDI"):
        CoveragePolicy.from_config(Config())


def test_missing_config_fields_use_frozen_defaults() -> None:
    class Config:
        pass

    assert CoveragePolicy.from_config(Config()) == CoveragePolicy.default()


def test_cli_reports_frozen_coverage_policy() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "src", "config"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=Path(__file__).resolve().parent.parent,
        check=True,
    )
    assert "image_coverage: 100% (required minimum)" in result.stdout
    assert "midi_coverage: 100% (required minimum)" in result.stdout


def test_v2_accepts_complete_media_and_rejects_incomplete_media() -> None:
    complete = validate_v2_package(FIXTURES / "complete.story")
    incomplete = validate_v2_package(FIXTURES / "media-coverage.story")

    assert complete.accepted
    assert not incomplete.accepted
    assert incomplete.issues[0].code == "PACKAGE_MEDIA_COVERAGE"
