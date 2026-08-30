"""WG-INTEGRATION-009 complete archive-input inventory evidence."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.storage.project_v2 import audit_package_inputs


def _copy_project(source: Path, target: Path) -> Path:
    shutil.copytree(source, target)
    return target


def test_package_audit_covers_every_authoritative_input(phase5_project) -> None:
    world, bible, narrative = phase5_project
    result = audit_package_inputs(world, bible, narrative)
    assert result.world_sources >= 37
    assert result.history_events > 0
    assert result.history_snapshots > 0
    assert result.local_sites > 0
    assert result.local_chunks > 0
    assert result.narrative_nodes > 0
    assert result.gm_entries > 0
    assert result.schemas >= 22


def test_package_audit_rejects_incomplete_media_inventory(tmp_path: Path, phase5_project) -> None:
    world, bible, source = phase5_project
    narrative = _copy_project(source, tmp_path / "narrative")
    media_path = narrative / "media.json"
    media = json.loads(media_path.read_text())
    media.pop(sorted(media)[0])
    media_path.write_text(json.dumps(media))
    with pytest.raises(ValueError, match="PACKAGE-INPUT-MEDIA"):
        audit_package_inputs(world, bible, narrative)


def test_package_audit_rejects_missing_local_chunk(tmp_path: Path, phase5_project) -> None:
    world, bible, source = phase5_project
    narrative = _copy_project(source, tmp_path / "narrative")
    chunk = sorted((narrative / "local_chunks").rglob("*.json"))[0]
    chunk.unlink()
    with pytest.raises(ValueError, match="PACKAGE-INPUT-LOCAL:.*local chunk inventory mismatch"):
        audit_package_inputs(world, bible, narrative)


def test_package_audit_requires_accepted_reconciliation(tmp_path: Path, phase5_project) -> None:
    world, source_bible, narrative = phase5_project
    bible = _copy_project(source_bible, tmp_path / "bible")
    report_path = bible / "reconciliation.json"
    report = json.loads(report_path.read_text())
    report["accepted"] = False
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="PACKAGE-INPUT-RECONCILIATION"):
        audit_package_inputs(world, bible, narrative)
