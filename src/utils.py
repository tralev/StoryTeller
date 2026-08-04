"""Shared utility helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Fixed anchor epoch for deterministic artifact timestamps. Values are
# synthetic — they identify the generation run, not a real clock reading.
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
_YEAR_SECONDS = 365 * 24 * 3600
# Knuth multiplicative hash constant — spreads consecutive seeds widely
# across the anchor year so different seeds get visibly different dates.
_SEED_SPREAD = 2654435761


def deterministic_created_at(seed: int) -> str:
    """RFC3339 timestamp that is a pure function of the run seed.

    Same seed + config must produce byte-identical artifacts (Phase 5.6D
    archive-level determinism). Wall-clock ``created_at`` values made
    content/* differ between two same-seed runs whenever the clock crossed
    a second boundary, breaking the determinism tests and the content hash.

    Deriving the timestamp from the seed keeps the schema-required field,
    keeps it a valid date-time string, and makes it reproducible: the same
    world always reports the same creation time.

    Operational wall-clock data still lives in manifest.meta.generated_at,
    which is excluded from canonical hashing.
    """
    offset = timedelta(seconds=(abs(int(seed)) * _SEED_SPREAD) % _YEAR_SECONDS)
    return (_EPOCH + offset).strftime("%Y-%m-%dT%H:%M:%SZ")
