"""WG-KERNEL-009 immutable reuse, verification, confinement, and crash safety."""
from __future__ import annotations

import json

import pytest

from src.worldgen.artifacts import WorldArtifact, WorldArtifactRepository, canonical_json


def artifact(payload: object = None, *, fingerprint: str = "tests:artifact:v1",
             dependencies: tuple[str, ...] = ()) -> WorldArtifact[object]:
    return WorldArtifact.build(
        "sample", {"value": 1} if payload is None else payload,
        depends_on=dependencies, producer_fingerprint=fingerprint,
    )


def test_exact_reuse_is_idempotent_but_conflicting_reuse_is_rejected(tmp_path):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    expected = artifact(dependencies=("source_0123456789abcdef0123456789abcdef",))
    path = repository.put(expected)
    before = path.read_bytes()
    assert repository.put(expected) == path
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="WG-REUSE"):
        repository.put(artifact({"value": 2}))
    with pytest.raises(ValueError, match="WG-REUSE"):
        repository.put(artifact(fingerprint="tests:artifact:v2"))


@pytest.mark.parametrize("field", ["sha256", "depends_on", "producer_fingerprint"])
def test_load_rejects_tampered_hash_dependency_or_fingerprint(tmp_path, field):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    path = repository.put(artifact())
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if field == "sha256":
        envelope[field] = "0" * 64
    elif field == "depends_on":
        envelope[field] = ["../escape"]
    else:
        envelope[field] = "invalid fingerprint with spaces"
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError):
        repository.load_verified("sample")


def test_load_rejects_kind_mismatch_extra_fields_and_noncanonical_json(tmp_path):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    path = repository.put(artifact())
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["kind"] = "other"
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="kind mismatch"):
        repository.load_verified("sample")
    envelope["kind"] = "sample"
    envelope["extra"] = 1
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="invalid world artifact"):
        repository.load_verified("sample")
    envelope.pop("extra")
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="noncanonical"):
        repository.load_verified("sample")


@pytest.mark.parametrize("kind", ["../escape", "a/b", ".", "UPPER", "a\\b"])
def test_repository_kind_paths_are_confined(tmp_path, kind):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="WG-PATH"):
        repository.load_verified(kind)


def test_interrupted_publication_leaves_no_target_or_temp_file(tmp_path, monkeypatch):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    import src.storage.fs as fs

    def fail_replace(source, destination):
        raise OSError("injected rename failure")

    monkeypatch.setattr(fs.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        repository.put(artifact())
    assert not (repository.root / "sample.json").exists()
    assert not (repository.root / "sample.json.tmp").exists()


def test_persisted_envelope_rejects_non_nfc_and_duplicate_normalized_keys(tmp_path):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    path = repository.put(artifact())
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"] = {"cafe\u0301": 1}
    path.write_text(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="noncanonical"):
        repository.load_verified("sample")

    encoded = path.read_text(encoding="utf-8").replace(
        '"café":1', '"café":1,"café":2',
    )
    path.write_text(encoded, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate object key"):
        repository.load_verified("sample")


def test_repository_rejects_legacy_payload_only_artifact_identity(tmp_path):
    repository = WorldArtifactRepository(tmp_path / "artifacts")
    path = repository.put(artifact())
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["artifact_id"] = "sample_" + envelope["sha256"][:32]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        repository.load_verified("sample")
