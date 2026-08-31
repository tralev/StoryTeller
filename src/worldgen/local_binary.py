"""Canonical uncompressed binary envelope for sparse site-local chunks."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping
from typing import Any, cast

from .artifacts import canonical_json

LOCAL_CHUNK_MAGIC = b"STLCBIN1"
LOCAL_CHUNK_FAMILIES = ("construction", "material", "occupancy")


def encode_local_chunk(family: str, payload: Mapping[str, object]) -> bytes:
    if family not in LOCAL_CHUNK_FAMILIES or "sha256" in payload:
        raise ValueError("WG-LOCAL-BINARY: invalid family or payload")
    header = canonical_json(
        {
            "format": "storyteller.local-chunk-binary.v1",
            "family": family,
            "payload": payload,
        }
    )
    return LOCAL_CHUNK_MAGIC + struct.pack(">I", len(header)) + header


def decode_local_chunk(encoded: bytes, family: str, expected_sha256: str) -> dict[str, Any]:
    if family not in LOCAL_CHUNK_FAMILIES or len(encoded) < len(LOCAL_CHUNK_MAGIC) + 4:
        raise ValueError("WG-LOCAL-BINARY: invalid envelope")
    if encoded[: len(LOCAL_CHUNK_MAGIC)] != LOCAL_CHUNK_MAGIC:
        raise ValueError("WG-LOCAL-BINARY: invalid magic")
    size_start = len(LOCAL_CHUNK_MAGIC)
    header_size = struct.unpack(">I", encoded[size_start : size_start + 4])[0]
    header = encoded[len(LOCAL_CHUNK_MAGIC) + 4 :]
    if header_size != len(header) or hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("WG-LOCAL-BINARY: length or hash mismatch")
    import json

    value = json.loads(header)
    if (
        not isinstance(value, dict)
        or set(value) != {"format", "family", "payload"}
        or value["format"] != "storyteller.local-chunk-binary.v1"
        or value["family"] != family
        or not isinstance(value["payload"], dict)
        or canonical_json(value) != header
    ):
        raise ValueError("WG-LOCAL-BINARY: noncanonical or mismatched header")
    payload = cast(dict[str, Any], value["payload"])
    payload["sha256"] = expected_sha256
    return payload
