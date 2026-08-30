"""Deterministic, vector-like heraldry with cited cultural meanings."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..numeric import identity, rng_for_decision, stable_id
from .registries import simulation_registry_entries

_HEX = re.compile(r"^#[0-9A-F]{6}$")
MIN_LUMINANCE_DIFFERENCE_PPM = 300_000


@dataclass(frozen=True)
class HeraldicColor:
    color_id: str
    hex_rgb: str
    luminance_ppm: int


@dataclass(frozen=True)
class HeraldicMotif:
    motif_id: str
    center_x_ppm: int
    center_y_ppm: int
    size_ppm: int
    meaning: str
    meaning_source_kind: str
    meaning_source_id: str


@dataclass(frozen=True)
class VectorHeraldry:
    heraldry_id: str
    aspect_width: int
    aspect_height: int
    field_division: str
    division_angle_millidegrees: int
    primary: HeraldicColor
    secondary: HeraldicColor
    motif: HeraldicMotif


def _entry(entry_id: str) -> Mapping[str, object]:
    return next(
        entry for entry in simulation_registry_entries("language") if entry["id"] == entry_id
    )


def _colors() -> tuple[HeraldicColor, ...]:
    raw_colors = _entry("heraldry_palette_v1")["colors"]
    if not isinstance(raw_colors, tuple):
        raise ValueError("WG-HERALDRY-PALETTE: colors must be a tuple")
    colors = []
    for raw in raw_colors:
        if not isinstance(raw, Mapping):
            raise ValueError("WG-HERALDRY-PALETTE: color must be a mapping")
        luminance = raw["luminance_ppm"]
        if isinstance(luminance, bool) or not isinstance(luminance, int):
            raise ValueError("WG-HERALDRY-PALETTE: luminance must be an integer")
        colors.append(HeraldicColor(str(raw["id"]), str(raw["hex_rgb"]), luminance))
    return tuple(colors)


def _nonempty_tuple(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"WG-HERALDRY-REGISTRY: invalid {label}")
    return value


def validate_heraldry(design: VectorHeraldry) -> None:
    if design.aspect_width <= 0 or design.aspect_height <= 0:
        raise ValueError("WG-HERALDRY-ASPECT: dimensions must be positive")
    divisions = _entry("heraldry_design_v1")["divisions"]
    motifs = _entry("heraldry_design_v1")["motifs"]
    if not isinstance(divisions, tuple) or design.field_division not in divisions:
        raise ValueError("WG-HERALDRY-DIVISION: unregistered field division")
    if not isinstance(motifs, tuple) or design.motif.motif_id not in motifs:
        raise ValueError("WG-HERALDRY-MOTIF: unregistered overlay motif")
    registered_colors = {color.color_id: color for color in _colors()}
    if len(registered_colors) != len(_colors()):
        raise ValueError("WG-HERALDRY-PALETTE: duplicate color ID")
    for color in (design.primary, design.secondary):
        if not _HEX.fullmatch(color.hex_rgb) or not 0 <= color.luminance_ppm <= 1_000_000:
            raise ValueError("WG-HERALDRY-COLOR: invalid vector color")
        if registered_colors.get(color.color_id) != color:
            raise ValueError("WG-HERALDRY-COLOR: color does not match the registry")
    if (
        design.primary.color_id == design.secondary.color_id
        or abs(design.primary.luminance_ppm - design.secondary.luminance_ppm)
        < MIN_LUMINANCE_DIFFERENCE_PPM
    ):
        raise ValueError("WG-HERALDRY-CONTRAST: field colors lack required contrast")
    if not -180_000 <= design.division_angle_millidegrees <= 180_000:
        raise ValueError("WG-HERALDRY-VECTOR: invalid division angle")
    motif = design.motif
    if (
        not 0 <= motif.center_x_ppm <= 1_000_000
        or not 0 <= motif.center_y_ppm <= 1_000_000
        or not 1 <= motif.size_ppm <= 1_000_000
    ):
        raise ValueError("WG-HERALDRY-VECTOR: motif parameters out of bounds")
    if (
        motif.meaning_source_kind not in {"culture_trait", "history_event"}
        or not motif.meaning_source_id
        or not motif.meaning
    ):
        raise ValueError("WG-HERALDRY-CITATION: motif meaning lacks a culture/history source")


def generate_heraldry(
    seed: int, entity_id: str, culture_traits: tuple[str, ...], culture_source_id: str
) -> VectorHeraldry:
    if not culture_traits or not culture_source_id:
        raise ValueError("WG-HERALDRY-CITATION: cultural source is required")
    design_registry = _entry("heraldry_design_v1")
    divisions = _nonempty_tuple(design_registry["divisions"], "divisions")
    motifs = _nonempty_tuple(design_registry["motifs"], "motifs")
    angles = _nonempty_tuple(design_registry["angles_millidegrees"], "angles")
    colors = _colors()
    pairs = tuple(
        (left, right)
        for left in colors
        for right in colors
        if left.color_id != right.color_id
        and abs(left.luminance_ppm - right.luminance_ppm) >= MIN_LUMINANCE_DIFFERENCE_PPM
    )
    if not pairs:
        raise ValueError("WG-HERALDRY-CONTRAST: palette has no valid pair")
    rng = rng_for_decision(seed, "civilization.heraldry", entity_id, culture_source_id)
    primary, secondary = pairs[rng.below(len(pairs))]
    trait = culture_traits[rng.below(len(culture_traits))]
    motif_id = str(motifs[rng.below(len(motifs))])
    heraldry_id = stable_id("heraldry", seed, identity("entity_id", entity_id))
    motif = HeraldicMotif(
        motif_id,
        500_000,
        500_000,
        360_000,
        f"The {motif_id} represents {trait}.",
        "culture_trait",
        culture_source_id,
    )
    angle = angles[rng.below(len(angles))]
    if isinstance(angle, bool) or not isinstance(angle, int):
        raise ValueError("WG-HERALDRY-REGISTRY: angle must be an integer")
    result = VectorHeraldry(
        heraldry_id,
        3,
        2,
        str(divisions[rng.below(len(divisions))]),
        angle,
        primary,
        secondary,
        motif,
    )
    validate_heraldry(result)
    return result
