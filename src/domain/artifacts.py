"""Canonical artifact identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from typing_extensions import TypeAlias

ArtifactKey: TypeAlias = Literal[
    "world_snapshot", "world_physical", "world", "bible", "reconciliation",
    "style_bible", "story", "graph", "narrative_project", "media_intents", "local_maps", "media", "images", "midi",
    "gm_index", "manifest", "package_candidate", "package_acceptance", "packager",
]

CANONICAL_ARTIFACT_KEYS: frozenset[str] = frozenset({
    "world_snapshot", "world_physical", "world", "bible", "reconciliation",
    "style_bible", "story", "graph", "narrative_project", "media_intents", "local_maps", "media", "images", "midi",
    "gm_index", "manifest", "package_candidate", "package_acceptance", "packager",
})

STEP_ARTIFACT_KEYS: dict[str, ArtifactKey] = {
    "physical_world": "world_physical", "simulate_world": "world",
    "world_builder_v2": "bible", "reconcile_world": "reconciliation",
    "art_direction_v2": "style_bible",
    "story_v2": "story", "graph_v2": "narrative_project",
    "media_intents_v2": "media_intents",
    "image_media_v2": "images", "local_maps_v2": "local_maps",
    "music_media_v2": "midi", "accept_media_v2": "media", "gm_index_v2": "gm_index",
    "package_v2": "package_candidate",
    "accept_package_v2": "package_acceptance", "packager": "packager",
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
