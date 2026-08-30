from __future__ import annotations

from src.worldgen.reference import (
    REFERENCE_EVENT_COUNT,
    REFERENCE_SHA256,
    REFERENCE_SITES,
    REFERENCE_SIZE,
    verify_reference,
)


def test_embedded_reference_vector() -> None:
    assert verify_reference() == {
        "byte_length": REFERENCE_SIZE,
        "sha256": REFERENCE_SHA256,
        "site_indices": REFERENCE_SITES,
        "event_count": REFERENCE_EVENT_COUNT,
    }
