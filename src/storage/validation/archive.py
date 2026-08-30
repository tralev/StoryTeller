"""Streaming ZIP/JSON security, artifact inventory, and content identity."""

from __future__ import annotations

import codecs
import hashlib
import stat
import zipfile
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

from .common import CanonicalEncoder, JsonLoader, PackageV2Error
from .manifest import HASH_RE, ID_RE, validate_artifact_dag, validate_producer

MAX_ENTRIES = 100_000
MAX_MEMBER_BYTES = 4 * 1024 * 1024 * 1024
MAX_TOTAL_DECLARED_BYTES = 1 << 45
MAX_COMPRESSION_RATIO = 1_000
MAX_JSON_DEPTH = 128

PathNormalizer = Callable[[str], str]
ContentHash = Callable[[Iterable[Mapping[str, Any]]], str]


class ArtifactRecordFactory(Protocol):
    def __call__(
        self, kind: str, path: str, data: bytes, *,
        depends_on: Iterable[str] = (),
        producer_data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ArchiveInspection:
    names: frozenset[str]
    total_bytes: int


def inspect_archive_security(
    archive: zipfile.ZipFile,
    normalize_path: PathNormalizer,
    load_json: JsonLoader,
) -> ArchiveInspection:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise PackageV2Error("PACKAGE_ENTRY_LIMIT", "too many entries")
    ordered_names = [info.filename for info in infos]
    if ordered_names != sorted(ordered_names, key=lambda name: name.encode("utf-8")):
        raise PackageV2Error(
            "PACKAGE_PATH_ORDER", "entries are not sorted by UTF-8 path bytes"
        )
    names: set[str] = set()
    total = 0
    for info in infos:
        name = normalize_path(info.filename)
        if name in names:
            raise PackageV2Error("PACKAGE_DUPLICATE_PATH", "duplicate entry", name)
        names.add(name)
        total += info.file_size
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise PackageV2Error("PACKAGE_LINK", "links are forbidden", name)
        if info.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_DECLARED_BYTES:
            raise PackageV2Error(
                "PACKAGE_SIZE_LIMIT", "declared size exceeds security limit", name
            )
        if info.file_size > 0 and (
            info.compress_size <= 0
            or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise PackageV2Error(
                "PACKAGE_COMPRESSION_LIMIT", "compression amplification", name
            )
    if archive.comment:
        raise PackageV2Error("PACKAGE_ZIP_METADATA", "archive comment is forbidden")
    for info in infos:
        expected_compression = (
            zipfile.ZIP_STORED if info.filename.endswith(".png") else zipfile.ZIP_DEFLATED
        )
        mode = info.external_attr >> 16
        if (
            info.date_time != (1980, 1, 1, 0, 0, 0)
            or not stat.S_ISREG(mode)
            or stat.S_IMODE(mode) != 0o644
            or info.extra
            or info.comment
            or info.compress_type != expected_compression
        ):
            raise PackageV2Error(
                "PACKAGE_ZIP_METADATA", "entry metadata is not canonical", info.filename
            )
    for info in infos:
        if info.filename.endswith(".bin"):
            with archive.open(info) as member:
                prefix = member.read(8)
            if _secondary_compression(prefix):
                raise PackageV2Error(
                    "PACKAGE_SECONDARY_COMPRESSION",
                    "raw binary chunks cannot contain another compression wrapper",
                    info.filename,
                )
    for info in infos:
        if info.filename.endswith(".json"):
            with archive.open(info) as member:
                encoding_code = _json_encoding_code(member)
            if encoding_code:
                raise PackageV2Error(
                    encoding_code, "JSON must be BOM-free valid UTF-8", info.filename
                )
            with archive.open(info) as member:
                if _json_depth_exceeded(member):
                    raise PackageV2Error(
                        "PACKAGE_JSON_DEPTH", "JSON nesting exceeds 128 levels", info.filename
                    )
            load_json(archive.read(info), info.filename)
    if any(_forbidden_member(name) for name in names):
        raise PackageV2Error("PACKAGE_FORBIDDEN_ENTRY", "v1/save layout is forbidden")
    if "manifest.json" not in names:
        raise PackageV2Error("PACKAGE_MISSING_MANIFEST", "manifest is required")
    return ArchiveInspection(frozenset(names), total)


def validate_canonical_json_members(
    archive: zipfile.ZipFile,
    load_json: JsonLoader,
    canonical_json: CanonicalEncoder,
) -> None:
    for info in archive.infolist():
        if info.filename.endswith(".json"):
            data = archive.read(info)
            if canonical_json(load_json(data, info.filename)) != data:
                raise PackageV2Error(
                    "PACKAGE_JSON_NONCANONICAL", "JSON is not canonical JCS", info.filename
                )


def validate_artifact_inventory(
    archive: zipfile.ZipFile,
    names: set[str],
    manifest: Mapping[str, Any],
    normalize_path: PathNormalizer,
    load_json: JsonLoader,
    canonical_json: CanonicalEncoder,
    artifact_record: ArtifactRecordFactory,
    content_hash: ContentHash,
) -> None:
    records = manifest.get("artifacts")
    if not isinstance(records, list):
        raise PackageV2Error("PACKAGE_INVENTORY", "artifacts must be array")
    artifact_paths = [
        record.get("path") for record in records if isinstance(record, dict)
    ]
    if artifact_paths != sorted(
        artifact_paths, key=lambda value: str(value).encode("utf-8")
    ):
        raise PackageV2Error(
            "PACKAGE_ARRAY_ORDER", "artifact records must use UTF-8 path order"
        )
    by_id: dict[str, dict[str, Any]] = {}
    declared: set[str] = {"manifest.json"}
    record_data: dict[str, bytes] = {}
    for record in records:
        if not isinstance(record, dict):
            raise PackageV2Error("PACKAGE_INVENTORY", "invalid record")
        path = normalize_path(record.get("path", ""))
        artifact_id = record.get("artifact_id", "")
        if not ID_RE.fullmatch(artifact_id) or not HASH_RE.fullmatch(
            record.get("sha256", "")
        ):
            raise PackageV2Error(
                "PACKAGE_IDENTITY", "invalid artifact ID or SHA-256", path
            )
        if path in declared or artifact_id in by_id:
            raise PackageV2Error("PACKAGE_DUPLICATE_ID", "duplicate path or ID", path)
        if path not in names:
            raise PackageV2Error(
                "PACKAGE_MISSING_ARTIFACT", "declared file missing", path
            )
        data = archive.read(path)
        if (
            len(data) != record.get("size_bytes")
            or hashlib.sha256(data).hexdigest() != record["sha256"]
        ):
            raise PackageV2Error(
                "PACKAGE_HASH_MISMATCH", "artifact bytes do not match", path
            )
        if path.endswith(".json") or path.endswith(".schema.json"):
            value = load_json(data, path)
            if canonical_json(value) != data:
                raise PackageV2Error(
                    "PACKAGE_JSON_NONCANONICAL", "JSON is not canonical JCS", path
                )
        declared.add(path)
        by_id[artifact_id] = record
        record_data[artifact_id] = data
    if names != declared:
        raise PackageV2Error(
            "PACKAGE_UNDECLARED_ENTRY", "archive has undeclared entries",
            sorted(names - declared)[0],
        )
    validate_artifact_dag(by_id)
    for artifact_id, record in by_id.items():
        path = record["path"]
        validate_producer(record.get("producer"), path)
        expected = artifact_record(
            record["kind"], path, record_data[artifact_id],
            depends_on=record.get("depends_on", ()),
            producer_data=record.get("producer"),
        )
        if expected["artifact_id"] != artifact_id:
            raise PackageV2Error(
                "PACKAGE_ARTIFACT_ID", "artifact ID derivation mismatch", path
            )
    actual_hash = content_hash(records)
    if (
        manifest.get("content_hash") != actual_hash
        or manifest.get("story_id") != f"story_{actual_hash[:32]}"
    ):
        raise PackageV2Error("PACKAGE_CONTENT_ID", "content/story identity mismatch")


def _secondary_compression(prefix: bytes) -> bool:
    signatures = (
        b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00", b"\x28\xb5\x2f\xfd",
        b"PK\x03\x04", b"\x04\x22\x4d\x18",
    )
    return any(prefix.startswith(signature) for signature in signatures)


def _forbidden_member(path: str) -> bool:
    lowered = path.lower()
    forbidden_suffixes = (
        ".app", ".apk", ".bat", ".cmd", ".dll", ".dylib", ".exe", ".gguf",
        ".html", ".htm", ".jar", ".js", ".model", ".safetensors", ".sh", ".so",
    )
    return (
        path == "save" or path.startswith("save/") or path.startswith("content/")
        or lowered.endswith(forbidden_suffixes)
    )


def _json_depth_exceeded(stream: Any) -> bool:
    depth = 0
    in_string = False
    escaped = False
    while chunk := stream.read(64 * 1024):
        for value in chunk:
            if in_string:
                if escaped:
                    escaped = False
                elif value == 0x5C:
                    escaped = True
                elif value == 0x22:
                    in_string = False
            elif value == 0x22:
                in_string = True
            elif value in (0x7B, 0x5B):
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    return True
            elif value in (0x7D, 0x5D):
                depth -= 1
    return False


def _json_encoding_code(stream: Any) -> str | None:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    prefix = b""
    try:
        while chunk := stream.read(64 * 1024):
            if len(prefix) < 3:
                prefix += chunk[: 3 - len(prefix)]
            decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "PACKAGE_JSON_UTF8"
    return "PACKAGE_JSON_BOM" if prefix == b"\xef\xbb\xbf" else None
