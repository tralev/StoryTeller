"""Typed composition boundaries — artifact keys, run spec, and JSON boundary models.

Phase 5.6N: Replaces bare string keys and ``dict[str, Any]`` at pipeline
composition boundaries with typed constants (N1), a typed run specification
(N4), and TypedDict boundary models mirroring the JSON Schemas (N3).

This module is a leaf in the dependency graph: it imports nothing from the
project, so any layer (job_queue, models, application) may import it without
creating cycles.

Layout:
    - ArtifactKey / CANONICAL_ARTIFACT_KEYS  (N1)
    - RunSpec                                 (N4)
    - TypedDict boundary models               (N3)
"""

from __future__ import annotations

from typing import Any

# NotRequired/TypedDict: typing_extensions is required for Python 3.9
# (typing.NotRequired only exists on 3.11+). typing_extensions is a hard
# transitive dependency (pydantic>=2.5 requires it).
from typing_extensions import NotRequired, TypedDict

from ..domain.artifacts import (
    CANONICAL_ARTIFACT_KEYS as CANONICAL_ARTIFACT_KEYS,
)
from ..domain.artifacts import (
    ArtifactKey as ArtifactKey,
)
from ..domain.artifacts import (
    is_artifact_key as is_artifact_key,
)
from ..domain.run_spec import RunSpec as RunSpec

# ─────────────────────────────────────────────────────────────────────
# N1: Canonical artifact keys
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# N3: TypedDict boundary models (mirror the JSON Schemas in schemas/)
# ─────────────────────────────────────────────────────────────────────

# ── Graph ─────────────────────────────────────────────────────────────


class ChoiceDict(TypedDict):
    """One choice edge in a graph node (graph.schema.json #/definitions/choice)."""

    choice_id: str
    choice_text: str
    target_node: str
    requires_flags: NotRequired[list[str]]
    forbids_flags: NotRequired[list[str]]
    sets_flags: NotRequired[list[str]]
    consequence_hint: NotRequired[str]


class ConditionalTextDict(TypedDict):
    """Conditional text appended when a flag is set."""

    if_flag: str
    append: str


class GraphNodeEndingsDict(TypedDict, total=False):
    """Ending metadata for terminal nodes."""

    is_ending: bool
    ending_type: str  # "dark" | "bittersweet" | "good"
    ending_title: str
    conditions: list[str]
    epitaph: str


class GraphNodeDict(TypedDict, total=False):
    """A single CYOA node (graph.schema.json #/definitions/node).

    Required by the schema: node_id, chapter, scene_type, text,
    present_characters, present_location, mood, choices.
    Optional: present_creatures, image_prompt, music_tone,
    conditional_text, on_enter, endings.
    """

    node_id: str
    chapter: int
    scene_type: str
    text: str
    present_characters: list[str]
    present_location: str
    present_creatures: list[str]
    mood: str
    image_prompt: str
    music_tone: str
    choices: list[ChoiceDict]
    conditional_text: list[ConditionalTextDict]
    endings: GraphNodeEndingsDict


class EndingSummaryDict(TypedDict, total=False):
    """One entry in graph.endings_summary."""

    node_id: str
    type: str  # "dark" | "bittersweet" | "good"
    title: str
    condition_count: int


class GraphDict(TypedDict, total=False):
    """The branching CYOA graph (graph.schema.json)."""

    schema_version: int
    generator_version: str
    pipeline_version: int
    created_at: str
    model_versions: dict[str, str]
    seed: int
    starting_node: str
    flags_catalog: dict[str, str]
    nodes: list[GraphNodeDict]
    endings_summary: list[EndingSummaryDict]


# ── Bible ─────────────────────────────────────────────────────────────


class BibleDict(TypedDict, total=False):
    """The World Bible (bible.schema.json) — top-level shape only.

    The nested entity/system structures are intentionally left as
    ``dict[str, Any]`` — this boundary model exists to type the
    artifact repository surface, not to re-implement the full schema.
    """

    schema_version: int
    generator_version: str
    pipeline_version: int
    created_at: str
    model_versions: dict[str, str]
    seed: int
    generation_params: dict[str, Any]
    world_name: str
    narrative_rules: dict[str, Any]
    entities: dict[str, Any]
    systems: dict[str, Any]


# ── Story / Style Bible / GM Index ────────────────────────────────────


class StoryDict(TypedDict, total=False):
    """The linear story (story.schema.json) — top-level shape."""

    schema_version: int
    generator_version: str
    pipeline_version: int
    created_at: str
    model_versions: dict[str, str]
    seed: int
    title: str
    chapters: list[dict[str, Any]]


class StyleBibleDict(TypedDict, total=False):
    """Art style bible (style_bible.schema.json) — top-level shape."""

    schema_version: int
    generator_version: str
    seed: int
    art_style: dict[str, Any]
    character_design: dict[str, Any]
    location_palettes: dict[str, Any]


class GmIndexDict(TypedDict, total=False):
    """Game Master retrieval index (gm_index.schema.json) — top-level shape."""

    schema_version: int
    generator_version: str
    seed: int
    entities: dict[str, Any]
    nodes: dict[str, Any]


# ── Manifest ──────────────────────────────────────────────────────────


class ManifestMetaDict(TypedDict, total=False):
    """Operational metadata — varies per run, NOT part of artifact identity."""

    artifact_id: str
    generated_at: str
    run_id: str
    generation_time_seconds: float
    peak_ram_mb: float


class ProvenanceProducedByDict(TypedDict, total=False):
    """X3: model + prompt version that produced one artifact."""

    model: str
    model_hash: str
    prompt_version: str


class ProvenanceDict(TypedDict, total=False):
    """Phase 5.6X: artifact provenance — why does this artifact exist?

    - inventory:  content-derived canonical artifact ID per artifact key (X1)
    - depends_on: upstream artifact IDs each artifact derives from (X2)
    - produced_by: model + prompt hash per producing artifact (X3)
    """

    inventory: dict[str, str]
    depends_on: dict[str, list[str]]
    produced_by: dict[str, ProvenanceProducedByDict]


class ManifestStatsDict(TypedDict, total=False):
    """Canonical content-derived stats.

    total_thumbnails / total_midi_files are written by the Packager
    (file-count operational stats) in addition to the schema's totals.
    Phase 5.6 Q3: nodes_with_image_prompt / nodes_with_music_tone /
    quarantined_* / missing_* record the media coverage inventory.
    """

    total_nodes: int
    total_images: int
    total_midi: int
    total_endings: int
    total_thumbnails: int
    total_midi_files: int
    nodes_with_image_prompt: int
    nodes_with_music_tone: int
    quarantined_images: int
    quarantined_midi: int
    missing_images: int
    missing_midi: int


class ManifestDict(TypedDict, total=False):
    """Top-level manifest (manifest.schema.json).

    Required by the schema: schema_version, story_id, title,
    generator_version, models_used, prompt_versions, entry_point, files.
    """

    schema_version: int
    story_id: str
    title: str
    tone: str
    seed: int
    generator_version: str
    models_used: dict[str, str]
    prompt_versions: dict[str, str]
    entry_point: str
    provenance: ProvenanceDict
    files: dict[str, str]
    content_hash: str
    stats: ManifestStatsDict
    meta: ManifestMetaDict


# ── Media metadata ────────────────────────────────────────────────────


class ImageMetaDict(TypedDict, total=False):
    """Per-node image metadata stored in the images output."""

    size: tuple[int, int]
    seed: int
    prompt: str
    image_path: str
    thumb_path: str
    image_bytes: int


class ImagesOutputDict(TypedDict, total=False):
    """Aggregated images artifact: {images: {node_id: meta}, image_count, ...}."""

    images: dict[str, ImageMetaDict]
    image_count: int
    total_bytes: int
    quarantined: int
    skipped: int


class MidiMetaDict(TypedDict, total=False):
    """Per-node MIDI metadata stored in the midi output."""

    abc_notation: str
    midi_path: str
    midi_bytes: int
    music_tone: str
    seed: int


class MidiOutputDict(TypedDict, total=False):
    """Aggregated midi artifact: {midi: {node_id: meta}, midi_count, ...}."""

    midi: dict[str, MidiMetaDict]
    midi_count: int
    quarantined: int
    skipped: int


class PackageResultDict(TypedDict, total=False):
    """Packager result dict stored under ctx.outputs['packager']."""

    package_path: str
    package_size: int
    content_hash: str
    image_count: int
    midi_count: int
    # Phase 5.6 Q5: media completeness recorded by the acceptance gate.
    media_complete: bool
    coverage: dict[str, float]
