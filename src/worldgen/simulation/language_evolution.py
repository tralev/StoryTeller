"""Deterministic syllable realization, name safety, and historical sound change."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from .registries import simulation_registry_entries


@dataclass(frozen=True)
class LanguageStage:
    language_id: str
    year: int
    morphemes: tuple[str, ...]
    applied_shift_ids: tuple[str, ...]


def _entry(entry_id: str) -> Mapping[str, object]:
    return next(
        entry for entry in simulation_registry_entries("language") if entry["id"] == entry_id
    )


def realize_syllable(pattern: str, onset: str, vowel: str, coda: str) -> str:
    """Realize the closed C/V grammar, using coda for the final consonant."""
    realizations = {"CV": onset + vowel, "CVC": onset + vowel + coda, "VC": vowel + coda}
    if pattern not in realizations:
        raise ValueError(f"WG-LANGUAGE-PATTERN: {pattern}")
    result = realizations[pattern]
    if not result:
        raise ValueError("WG-LANGUAGE-SYLLABLE: empty realization")
    return result


def name_skeleton(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    confusables = _entry("name_safety_v1")["confusables"]
    if not isinstance(confusables, Mapping):
        raise ValueError("WG-NAME-SAFETY: invalid confusable registry")
    return "".join(
        str(confusables.get(character, character))
        for character in normalized
        if character.isalnum()
    )


def validate_name(candidate: str, used: set[str]) -> None:
    policy = _entry("name_safety_v1")
    skeleton = name_skeleton(candidate)
    reserved_raw = policy["reserved"]
    prohibited_raw = policy["prohibited_fragments"]
    if not isinstance(reserved_raw, tuple) or not isinstance(prohibited_raw, tuple):
        raise ValueError("WG-NAME-SAFETY: invalid name lists")
    reserved = {name_skeleton(str(value)) for value in reserved_raw}
    prohibited = tuple(name_skeleton(str(value)) for value in prohibited_raw)
    used_skeletons = {name_skeleton(value) for value in used}
    if not skeleton or skeleton in reserved:
        raise ValueError(f"WG-NAME-RESERVED: {candidate}")
    if any(fragment and fragment in skeleton for fragment in prohibited):
        raise ValueError(f"WG-NAME-PROHIBITED: {candidate}")
    if skeleton in used_skeletons:
        raise ValueError(f"WG-NAME-DUPLICATE: {candidate}")


def evolve_language(
    language_id: str, morphemes: tuple[str, ...], history_years: int
) -> tuple[LanguageStage, ...]:
    if history_years < 0:
        raise ValueError("WG-LANGUAGE-YEAR: history years must be nonnegative")
    shifts_raw = _entry("sound_shifts_v1")["rules"]
    if not isinstance(shifts_raw, tuple):
        raise ValueError("WG-LANGUAGE-SHIFTS: rules must be a tuple")
    current = morphemes
    stages = [LanguageStage(language_id, 0, current, ())]
    applied: list[str] = []
    for raw in shifts_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("WG-LANGUAGE-SHIFTS: rule must be a mapping")
        year = int(raw["year"])
        if year > history_years:
            continue
        source, target = str(raw["from"]), str(raw["to"])
        current = tuple(value.replace(source, target) for value in current)
        applied.append(str(raw["id"]))
        stages.append(LanguageStage(language_id, year, current, tuple(applied)))
    return tuple(stages)
