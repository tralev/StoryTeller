import json
import stat
import zipfile

from scripts.generate_v2_fixtures import build_complete, generate_schemas
from src.storage.package_v2 import (artifact_record, canonical_json, content_hash,
                                    validate_v2_package)


def test_acceptance_rejects_incomplete_world_source_ledger(tmp_path) -> None:
    generate_schemas()
    original = tmp_path / "original.story"
    changed = tmp_path / "changed.story"
    build_complete(original)
    with zipfile.ZipFile(original) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}

    ledger = json.loads(members["world/source/coverage.json"])
    ledger["sources"].pop()
    data = canonical_json(ledger)
    members["world/source/coverage.json"] = data
    manifest = json.loads(members["manifest.json"])
    record = next(item for item in manifest["artifacts"]
                  if item["path"] == "world/source/coverage.json")
    replacement = artifact_record(
        record["kind"], record["path"], data,
        depends_on=record["depends_on"], producer_data=record["producer"],
    )
    record.update(replacement)
    manifest["content_hash"] = content_hash(manifest["artifacts"])
    manifest["story_id"] = f"story_{manifest['content_hash'][:32]}"
    members["manifest.json"] = canonical_json(manifest)
    with zipfile.ZipFile(changed, "w") as archive:
        for path, value in sorted(members.items()):
            info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = (
                zipfile.ZIP_STORED if path.endswith(".png") else zipfile.ZIP_DEFLATED
            )
            archive.writestr(info, value)

    result = validate_v2_package(changed)
    assert not result.accepted
    assert result.issues[0].code == "PACKAGE_WORLD_SOURCE_COVERAGE"
