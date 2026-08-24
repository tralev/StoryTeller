"""Strict pre-freeze v2 narrative domain contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
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
    person_ids: tuple[str, ...] = ()
    belief_ids: tuple[str, ...] = ()
    site_ids: tuple[str, ...] = ()
    local_containment_ids: tuple[str, ...] = ()
    opportunity_kind: str = "faction_goal"
    answer_fact_ids: tuple[str, ...] = ()
    constraint_ids: tuple[str, ...] = ()
    role_assignments: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class StoryScene:
    scene_id: str
    title: str
    summary: str
    location_id: str
    participant_ids: tuple[str, ...]
    opportunity_id: str
    authoritative_refs: tuple[str, ...]
    world_year: int


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
    authoritative_refs: tuple[str, ...]
    transition_year: int
    season: int


@dataclass(frozen=True)
class MediaIntent:
    image_prompt: str
    music_mood: str
    tempo_bpm: int
    image_seed: int
    music_seed: int
    authoritative_refs: tuple[str, ...]


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
    world_year: int = 0


@dataclass(frozen=True)
class GraphV2:
    schema_version: str
    starting_node: str
    flags: tuple[str, ...]
    nodes: tuple[GraphNodeV2, ...]


SCORE_SCHEMA_VERSION = "storyteller.score.v1"
SCORE_PPQ = 960
# Sort rank for ScoreEvent.kind within a track: "ordered by start tick, event
# kind, pitch tuple, then event ID" (api.md). Alphabetical is the simplest
# stable, documented choice among the five literal kinds.
SCORE_EVENT_KINDS = ("chord", "control", "note", "pitch_bend", "rest")
SCORE_MARKER_NAMES = ("INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START")


@dataclass(frozen=True)
class Beat:
    """A reduced musical position/duration exactly representable at 960 PPQ."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.denominator <= 0:
            raise ValueError("BEAT-DENOMINATOR: denominator must be positive")
        if math.gcd(self.numerator, self.denominator) != 1:
            raise ValueError("BEAT-REDUCED: numerator/denominator must be in lowest terms")
        if (self.numerator * SCORE_PPQ) % self.denominator != 0:
            raise ValueError("BEAT-TICK: must map exactly to a 960 PPQ tick")

    @property
    def tick(self) -> int:
        return self.numerator * SCORE_PPQ // self.denominator

    @classmethod
    def from_tick(cls, tick: int) -> Beat:
        divisor = math.gcd(tick, SCORE_PPQ) or SCORE_PPQ
        return cls(tick // divisor, SCORE_PPQ // divisor)


@dataclass(frozen=True)
class ScoreEvent:
    event_id: str
    kind: str
    start: Beat
    duration: Beat
    pitches: tuple[int, ...] = ()
    velocity: int | None = None
    value: int | None = None


@dataclass(frozen=True)
class ScoreTrack:
    track_id: str
    role: str
    gm_program: int | None
    drum_channel: bool
    events: tuple[ScoreEvent, ...]


@dataclass(frozen=True)
class StructuredScore:
    schema_version: str
    node_id: str
    ppq: int
    duration: Beat
    tempo_map: tuple[Mapping[str, object], ...]
    time_signature_map: tuple[Mapping[str, object], ...]
    key_signature_map: tuple[Mapping[str, object], ...]
    tracks: tuple[ScoreTrack, ...]
    markers: Mapping[str, Beat]
    source_ids: tuple[str, ...]
    producer_fingerprint: str
    expected_midi_sha256: str


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
