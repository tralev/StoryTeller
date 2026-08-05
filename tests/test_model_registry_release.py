import hashlib
from pathlib import Path

from src.model_registry import ModelRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_release_registry_is_valid_and_immutable() -> None:
    model = ModelRegistry.load(ROOT / "config/model_registry.json").approved_for_role("game_master")
    assert model.revision in model.download_url
    assert "/resolve/main/" not in model.download_url
    assert model.byte_size == 2_019_377_696
    assert model.minimum_device.ram_bytes >= model.expected_peak_ram_bytes
    assert model.minimum_device.free_storage_bytes >= model.byte_size


def test_local_release_model_matches_allowlist_when_present() -> None:
    model = ModelRegistry.load(ROOT / "config/model_registry.json").approved_for_role("game_master")
    local = ROOT / "ai_models" / model.filename
    if not local.exists():
        return
    assert local.stat().st_size == model.byte_size
    digest = hashlib.sha256()
    with local.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    assert digest.hexdigest() == model.sha256


def test_native_registry_constants_do_not_drift() -> None:
    model = ModelRegistry.load(ROOT / "config/model_registry.json").approved_for_role("game_master")
    native_sources = (
        ROOT / "droid/app/src/main/java/com/storyteller/droid/model/ReleaseModelRegistry.kt",
        ROOT / "ios/StoryTeller/Model/ReleaseModelRegistry.swift",
    )
    canonical_values = (
        model.identifier,
        model.role,
        model.repository,
        model.revision,
        model.filename,
        model.sha256,
        model.license.url,
        model.license.notice,
    )
    for source in native_sources:
        text = source.read_text(encoding="utf-8")
        for value in canonical_values:
            assert value in text, f"{source} has drifted from the release registry: {value}"
