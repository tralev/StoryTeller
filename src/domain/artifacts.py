"""Canonical artifact identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from typing_extensions import TypeAlias

ArtifactKey: TypeAlias = Literal[
    "world_snapshot", "bible", "style_bible", "story", "graph",
    "images", "midi", "gm_index", "manifest", "packager",
]

CANONICAL_ARTIFACT_KEYS: frozenset[str] = frozenset({
    "world_snapshot", "bible", "style_bible", "story", "graph",
    "images", "midi", "gm_index", "manifest", "packager",
})

STEP_ARTIFACT_KEYS: dict[str, ArtifactKey] = {
    "procedural_world": "world_snapshot", "world_builder": "bible",
    "art_director": "style_bible", "story_writer": "story",
    "game_designer": "graph", "image_generator": "images",
    "music_generator": "midi", "indexer": "gm_index",
    "manifest_builder": "manifest", "packager": "packager",
}


def is_artifact_key(value: str) -> bool:
    return value in CANONICAL_ARTIFACT_KEYS


def artifact_key_for_step(step_id: str) -> str:
    return STEP_ARTIFACT_KEYS.get(step_id, step_id)


@dataclass(frozen=True)
class ArtifactRef:
    """Verified reference returned by every durable artifact write."""

    artifact_id: str
    kind: str
    canonical_path: str
    sha256: str
    size_bytes: int
    depends_on: tuple[str, ...] = ()
    producer_fingerprint: str = ""
