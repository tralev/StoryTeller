from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.application.generate_story import GenerateStory


class _Outputs:
    def __init__(self, packager: Any = None, manifest: Any = None) -> None:
        self._packager = packager
        self._manifest = manifest

    def get_packager(self) -> Any:
        return self._packager

    def get_manifest(self) -> Any:
        return self._manifest

    def items(self) -> tuple[tuple[str, Any], ...]:
        return ()


def test_build_result_handles_missing_packaging_outputs(tmp_path: Path) -> None:
    context = SimpleNamespace(
        state={"start_time": time.time()},
        outputs=_Outputs(),
    )
    manager = SimpleNamespace(peak_ram_mb=128, budget_mb=1024)

    result = GenerateStory._build_result(
        context,
        tmp_path,
        {},
        ["world simulation failed"],
        manager,
    )

    assert result.artifact_id == "unknown"
    assert result.package_path == ""
    assert result.package_size == 0
    assert result.image_coverage == 1.0
    assert result.midi_coverage == 1.0
    assert result.media_complete is False
    assert result.errors == ["world simulation failed"]


def test_build_result_handles_malformed_manifest_without_unbound_locals(tmp_path: Path) -> None:
    context = SimpleNamespace(
        state={"start_time": time.time()},
        outputs=_Outputs({"package_path": "candidate.story"}, "not-a-manifest"),
    )
    manager = SimpleNamespace(peak_ram_mb=128, budget_mb=1024)

    result = GenerateStory._build_result(context, tmp_path, {}, ["packaging failed"], manager)

    assert result.package_path == ""
    assert result.media_complete is False


def test_build_result_rejects_incomplete_packaging_success_shape(tmp_path: Path) -> None:
    context = SimpleNamespace(
        state={"start_time": time.time()},
        outputs=_Outputs(
            {"package_size": 123, "media_complete": True},
            {"content_hash": "a" * 64},
        ),
    )
    manager = SimpleNamespace(peak_ram_mb=128, budget_mb=1024)

    result = GenerateStory._build_result(context, tmp_path, {}, [], manager)

    assert result.artifact_id == "unknown"
    assert result.package_path == ""
    assert result.media_complete is False
    assert result.errors == ["packaging: required package path or content hash is missing"]
