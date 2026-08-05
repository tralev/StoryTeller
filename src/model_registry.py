"""Typed access to the release-pinned local model allowlist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


@dataclass(frozen=True)
class MinimumDevice:
    ram_bytes: int
    free_storage_bytes: int
    architectures: tuple[str, ...]


@dataclass(frozen=True)
class ModelLicense:
    identifier: str
    name: str
    upstream_repository: str
    upstream_revision: str
    url: str
    notice: str
    required_ui_attribution: str


@dataclass(frozen=True)
class ReleaseModel:
    identifier: str
    role: str
    display_name: str
    publisher: str
    distributor: str
    repository: str
    revision: str
    filename: str
    byte_size: int
    sha256: str
    quantization: str
    context_tokens: int
    expected_peak_ram_bytes: int
    minimum_device: MinimumDevice
    source_url: str
    download_url: str
    license: ModelLicense
    approved_uses: tuple[str, ...]
    release_status: str


class ModelRegistry:
    def __init__(self, models: tuple[ReleaseModel, ...]) -> None:
        self.models = models
        self._by_id = {model.identifier: model for model in models}
        if len(self._by_id) != len(models):
            raise ValueError("model registry contains duplicate IDs")

    def by_id(self, identifier: str) -> ReleaseModel:
        try:
            return self._by_id[identifier]
        except KeyError as exc:
            raise KeyError(f"unknown release model: {identifier}") from exc

    def approved_for_role(self, role: str) -> ReleaseModel:
        matches = [m for m in self.models if m.role == role and m.release_status == "approved"]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one approved model for role {role!r}")
        return matches[0]

    @classmethod
    def load(cls, path: Path | str, schema_path: Path | str | None = None) -> "ModelRegistry":
        registry_path = Path(path)
        schema = Path(schema_path) if schema_path else registry_path.parent.parent / "schemas/model-registry.schema.json"
        raw: Any = json.loads(registry_path.read_text(encoding="utf-8"))
        schema_raw: Any = json.loads(schema.read_text(encoding="utf-8"))
        Draft202012Validator(schema_raw, format_checker=FormatChecker()).validate(raw)
        if not isinstance(raw, Mapping):
            raise ValueError("model registry root must be an object")
        return cls(tuple(_parse_model(item) for item in raw["models"]))


def _parse_model(raw: Mapping[str, Any]) -> ReleaseModel:
    device = raw["minimum_device"]
    license_data = raw["license"]
    revision = str(raw["revision"])
    filename = str(raw["filename"])
    immutable_fragment = f"/resolve/{revision}/{filename}"
    if immutable_fragment not in str(raw["download_url"]):
        raise ValueError(f"model {raw['id']} download URL is not pinned to its revision")
    return ReleaseModel(
        identifier=str(raw["id"]), role=str(raw["role"]), display_name=str(raw["display_name"]),
        publisher=str(raw["publisher"]), distributor=str(raw["distributor"]), repository=str(raw["repository"]),
        revision=revision, filename=filename, byte_size=int(raw["byte_size"]), sha256=str(raw["sha256"]),
        quantization=str(raw["quantization"]), context_tokens=int(raw["context_tokens"]),
        expected_peak_ram_bytes=int(raw["expected_peak_ram_bytes"]),
        minimum_device=MinimumDevice(int(device["ram_bytes"]), int(device["free_storage_bytes"]), tuple(device["architectures"])),
        source_url=str(raw["source_url"]), download_url=str(raw["download_url"]),
        license=ModelLicense(str(license_data["id"]), str(license_data["name"]), str(license_data["upstream_repository"]), str(license_data["upstream_revision"]), str(license_data["url"]), str(license_data["notice"]), str(license_data["required_ui_attribution"])),
        approved_uses=tuple(raw["approved_uses"]), release_status=str(raw["release_status"]),
    )
