"""Objective magic laws and subjective belief institutions."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from ..numeric import identity, stable_id
from .registries import simulation_registry_entries


class EpistemicStatus(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNCERTAIN = "uncertain"
    METAPHORICAL = "metaphorical"


@dataclass(frozen=True)
class MagicLaw:
    law_id: str
    effect: str
    cost: str
    limit: str
    prohibited_effects: tuple[str, ...]


@dataclass(frozen=True)
class MagicSource:
    source_id: str
    vocabulary_id: str
    law_id: str
    location_id: str
    source_kind: str


@dataclass(frozen=True)
class MagicEffect:
    effect_id: str
    law_id: str
    source_id: str
    effect: str
    paid_cost: str
    side_effect: str
    location_id: str


@dataclass(frozen=True)
class Religion:
    religion_id: str
    belief_claim: str
    attributed_to: str
    epistemic_status: EpistemicStatus
    related_law_ids: tuple[str, ...]
    institution: str
    taboo: str
    holy_site_id: str


@dataclass(frozen=True)
class ReligiousInstitution:
    institution_id: str
    registry_id: str
    religion_id: str
    site_id: str
    rite: str


@dataclass(frozen=True)
class Schism:
    schism_id: str
    parent_religion_id: str
    child_institution_id: str
    disputed_claim: str


@dataclass(frozen=True)
class CulturalInterpretation:
    interpretation_id: str
    religion_id: str
    law_id: str
    attributed_to: str
    claim: str
    epistemic_status: EpistemicStatus


class SupernaturalBundle(NamedTuple):
    laws: tuple[MagicLaw, ...]
    sources: tuple[MagicSource, ...]
    effects: tuple[MagicEffect, ...]
    religions: tuple[Religion, ...]
    institutions: tuple[ReligiousInstitution, ...]
    schisms: tuple[Schism, ...]
    interpretations: tuple[CulturalInterpretation, ...]


def validate_supernatural(laws: tuple[MagicLaw, ...], sources: tuple[MagicSource, ...],
                          effects: tuple[MagicEffect, ...], religions: tuple[Religion, ...],
                          institutions: tuple[ReligiousInstitution, ...],
                          schisms: tuple[Schism, ...],
                          interpretations: tuple[CulturalInterpretation, ...]) -> None:
    law_ids = {law.law_id for law in laws}
    if len(law_ids) != len(laws):
        raise ValueError("WG-MAGIC-LAW-ID: duplicate objective law identity")
    source_ids = {source.source_id for source in sources}
    if (not sources or len(source_ids) != len(sources)
            or any(source.law_id not in law_ids or not source.location_id for source in sources)):
        raise ValueError("WG-MAGIC-SOURCE: invalid or duplicate place-bound source")
    for effect in effects:
        if effect.law_id not in law_ids or effect.source_id not in source_ids:
            raise ValueError(f"WG-MAGIC-EFFECT-SOURCE: {effect.effect_id}")
        law = next(item for item in laws if item.law_id == effect.law_id)
        source = next(item for item in sources if item.source_id == effect.source_id)
        if (effect.effect != law.effect or effect.paid_cost != law.cost or not effect.side_effect
                or source.law_id != law.law_id or source.location_id != effect.location_id):
            raise ValueError(f"WG-MAGIC-EFFECT-LAW: {effect.effect_id}")
    for religion in religions:
        if not religion.attributed_to or not isinstance(religion.epistemic_status, EpistemicStatus):
            raise ValueError(f"WG-MAGIC-BELIEF-ATTRIBUTION: {religion.religion_id}")
        if any(law_id not in law_ids for law_id in religion.related_law_ids):
            raise ValueError(f"WG-MAGIC-BELIEF-LAW: {religion.religion_id}")
    religion_ids = {religion.religion_id for religion in religions}
    institution_ids = {institution.institution_id for institution in institutions}
    if len(institution_ids) != len(institutions) or any(
            institution.religion_id not in religion_ids or not institution.rite
            for institution in institutions):
        raise ValueError("WG-MAGIC-INSTITUTION: invalid religious institution")
    if any(schism.parent_religion_id not in religion_ids
           or schism.child_institution_id not in institution_ids or not schism.disputed_claim
           for schism in schisms):
        raise ValueError("WG-MAGIC-SCHISM: invalid schism ancestry")
    if any(interpretation.religion_id not in religion_ids
           or interpretation.law_id not in law_ids or not interpretation.attributed_to
           or not isinstance(interpretation.epistemic_status, EpistemicStatus)
           for interpretation in interpretations):
        raise ValueError("WG-MAGIC-INTERPRETATION: invalid attributed interpretation")


def generate_supernatural(
    seed: int, site_ids: tuple[str, ...],
) -> SupernaturalBundle:
    vocabulary = simulation_registry_entries("magic_vocabulary")[0]
    belief = simulation_registry_entries("beliefs")[0]
    prohibited = vocabulary["prohibited"]
    if not isinstance(prohibited, tuple):
        raise ValueError("WG-MAGIC-REGISTRY: prohibited effects must be a tuple")
    law = MagicLaw(
        stable_id("magic_law", seed, identity("vocabulary_id", str(vocabulary["id"]))),
        "alter perceived light", str(vocabulary["cost"]), str(vocabulary["limit"]),
        tuple(str(value) for value in prohibited),
    )
    selected_sites = site_ids[:max(1, min(4, len(site_ids)))]
    sources = tuple(MagicSource(
        stable_id("magic_source", seed, identity("law_id", law.law_id),
                  identity("location_id", site_id)),
        str(vocabulary["id"]), law.law_id, site_id, str(vocabulary["source_kind"]),
    ) for site_id in selected_sites)
    effects = tuple(MagicEffect(
        stable_id("magic_effect", seed, identity("law_id", law.law_id),
                  identity("location_id", site_id)),
        law.law_id, source.source_id, law.effect, law.cost, str(vocabulary["side_effect"]), site_id,
    ) for site_id, source in zip(selected_sites[:1], sources[:1]))
    religions = tuple(Religion(
        stable_id("religion", seed, identity("holy_site_id", site_id)),
        str(belief["claim"]), str(belief["institution"]), EpistemicStatus.UNCERTAIN,
        (law.law_id,), str(belief["institution"]), str(belief["taboo"]), site_id,
    ) for site_id in selected_sites)
    institutions = tuple(ReligiousInstitution(
        stable_id("religious_institution", seed, identity("religion_id", religion.religion_id)),
        str(belief["institution"]), religion.religion_id, religion.holy_site_id,
        str(belief["rite"]),
    ) for religion in religions)
    schisms = tuple(Schism(
        stable_id("schism", seed, identity("parent_religion_id", religions[0].religion_id),
                  identity("child_institution_id", institution.institution_id)),
        religions[0].religion_id, institution.institution_id,
        f"whether {religions[0].belief_claim}",
    ) for institution in institutions[1:])
    interpretations = tuple(CulturalInterpretation(
        stable_id("magic_interpretation", seed, identity("religion_id", religion.religion_id),
                  identity("law_id", law.law_id)),
        religion.religion_id, law.law_id, institution.institution_id,
        f"{law.effect} is understood through {religion.belief_claim}",
        EpistemicStatus.METAPHORICAL,
    ) for religion, institution in zip(religions, institutions))
    result = SupernaturalBundle((law,), sources, effects, religions, institutions, schisms,
                                interpretations)
    validate_supernatural(result.laws, result.sources, result.effects, result.religions,
                          result.institutions, result.schisms, result.interpretations)
    return result
