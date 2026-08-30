import json
import shutil

import pytest

from src.narrative.pipeline import validate_project


def test_project_has_mandatory_100_percent_media(phase5_project):
    _, _, phase5 = phase5_project
    result = validate_project(phase5)
    coverage = json.loads((phase5 / "coverage.json").read_text())
    assert (
        result["nodes"]
        == coverage["images"]
        == coverage["thumbnails"]
        == coverage["scores"]
        == coverage["midi"]
    )


def test_missing_asset_never_validates_as_partial_success(tmp_path, phase5_project):
    _, _, phase5 = phase5_project
    copied = tmp_path / "project"
    shutil.copytree(phase5, copied)
    next((copied / "media" / "images").glob("*.png")).unlink()
    with pytest.raises(ValueError):
        validate_project(copied)
