"""Strict pre-freeze v2 narrative domain contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryOpportunity:
    opportunity_id: str
    pressure: str
    participant_ids: tuple[str, ...]
    location_ids: tuple[str, ...]
    route_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    revealable_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class StoryScene:
    scene_id: str
    title: str
    summary: str
    location_id: str
    participant_ids: tuple[str, ...]
    opportunity_id: str
    authoritative_refs: tuple[str, ...]


@dataclass(frozen=True)
class StoryV2:
    schema_version: str
    title: str
    world_artifact_ids: tuple[str, ...]
    bible_hash: str
    reconciliation_hash: str
    scenes: tuple[StoryScene, ...]


@dataclass(frozen=True)
class ChoiceV2:
    choice_id: str
    text: str
    target_node: str
    route_id: str | None
    sets_flags: tuple[str, ...]
    requires_flags: tuple[str, ...]


@dataclass(frozen=True)
class MediaIntent:
    image_prompt: str
    music_mood: str
    tempo_bpm: int
    image_seed: int
    music_seed: int


@dataclass(frozen=True)
class GraphNodeV2:
    node_id: str
    scene_id: str
    location_id: str
    participant_ids: tuple[str, ...]
    opportunity_id: str
    authoritative_refs: tuple[str, ...]
    text: str
    choices: tuple[ChoiceV2, ...]
    media_intent: MediaIntent
    ending: str | None = None


@dataclass(frozen=True)
class GraphV2:
    schema_version: str
    starting_node: str
    flags: tuple[str, ...]
    nodes: tuple[GraphNodeV2, ...]


@dataclass(frozen=True)
class ScoreNote:
    start_tick: int
    duration_ticks: int
    pitch: int
    velocity: int


@dataclass(frozen=True)
class StructuredScore:
    format_version: int
    ppq: int
    tempo_bpm: int
    loop_start_tick: int
    loop_end_tick: int
    program: int
    notes: tuple[ScoreNote, ...]


@dataclass(frozen=True)
class MediaRef:
    path: str
    sha256: str
    seed: int
    producer_fingerprint: str
    dependency_ids: tuple[str, ...]


@dataclass(frozen=True)
class NodeMedia:
    node_id: str
    image: MediaRef
    thumbnail: MediaRef
    score: MediaRef
    midi: MediaRef


@dataclass(frozen=True)
class KnowledgeEntry:
    entry_id: str
    kind: str
    normalized_text: str
    source_ids: tuple[str, ...]
    incoming_refs: tuple[str, ...]
    outgoing_refs: tuple[str, ...]
    reveal_after_nodes: tuple[str, ...]
