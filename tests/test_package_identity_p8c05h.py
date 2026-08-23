"""WG-INTEGRATION-010 canonical member identity and provenance evidence."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Callable

import pytest

from src.storage.package_v2 import (
    artifact_record,
    canonical_json,
    validate_v2_package,
)
from src.storage.project_v2 import package_project_v2


@pytest.fixture(scope="module")
def identity_package(tmp_path_factory: pytest.TempPathFactory, phase5_project: Any) -> Path:
    world, bible, narrative = phase5_project
    target = tmp_path_factory.mktemp("package-identity") / "identity.story"
    return package_project_v2(
        world, bible, narrative, target, title="Identity", seed=17,
    )


def _rewrite(
    source: Path,
    destination: Path,
    transform: Callable[[dict[str, bytes]], dict[str, bytes]],
    *,
    reverse: bool = False,
) -> Path:
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members = transform(members)
    names = sorted(members, reverse=reverse)
    with zipfile.ZipFile(destination, "w") as archive:
        for name in names:
            info = zipfile.ZipInfo(name, (2001, 2, 3, 4, 5, 6))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, members[name])
    return destination


def test_internal_member_hash_is_recomputed(identity_package: Path, tmp_path: Path) -> None:
    def corrupt(members: dict[str, bytes]) -> dict[str, bytes]:
        members["narrative/story.json"] += b" "
        return members

    result = validate_v2_package(
        _rewrite(identity_package, tmp_path / "corrupt.story", corrupt),
    )
    assert not result.accepted
    assert result.issues[0].code == "PACKAGE_HASH_MISMATCH"


def test_rederived_record_with_unknown_dependency_is_rejected(
    identity_package: Path, tmp_path: Path,
) -> None:
    def break_dag(members: dict[str, bytes]) -> dict[str, bytes]:
        manifest = json.loads(members["manifest.json"])
        record = next(
            item for item in manifest["artifacts"]
            if item["path"] == "assets/maps/world.png"
        )
        dependencies = [*record["depends_on"], f"missing_{'0' * 32}"]
        rebuilt = artifact_record(
            record["kind"], record["path"], members[record["path"]],
            depends_on=dependencies, producer_data=record["producer"],
        )
        record.clear()
        record.update(rebuilt)
        members["manifest.json"] = canonical_json(manifest)
        return members

    result = validate_v2_package(
        _rewrite(identity_package, tmp_path / "broken-dag.story", break_dag),
    )
    assert not result.accepted
    assert result.issues[0].code == "PACKAGE_PROVENANCE_BROKEN"


def test_zip_container_bytes_never_determine_story_identity(
    identity_package: Path, tmp_path: Path,
) -> None:
    original = validate_v2_package(identity_package)
    repacked_path = _rewrite(
        identity_package, tmp_path / "repacked.story", lambda members: members,
        reverse=True,
    )
    repacked = validate_v2_package(repacked_path)
    assert original.accepted and repacked.accepted
    assert original.manifest is not None and repacked.manifest is not None
    assert hashlib.sha256(identity_package.read_bytes()).digest() != hashlib.sha256(
        repacked_path.read_bytes(),
    ).digest()
    assert repacked.manifest["content_hash"] == original.manifest["content_hash"]
    assert repacked.manifest["story_id"] == original.manifest["story_id"]
