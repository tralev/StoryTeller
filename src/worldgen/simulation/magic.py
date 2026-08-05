"""Objective magic laws and subjective belief institutions."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import stable_id


@dataclass(frozen=True)
class MagicLaw:
    law_id: str
    effect: str
    cost: str
    limit: str
    prohibited_effects: tuple[str, ...]


@dataclass(frozen=True)
class Religion:
    religion_id: str
    belief_claim: str
    institution: str
    taboo: str
    holy_site_id: str


def generate_supernatural(seed: int, site_ids: tuple[str, ...]) -> tuple[tuple[MagicLaw, ...], tuple[Religion, ...]]:
    laws = (MagicLaw(stable_id("magic_law", seed, 0), "alter perceived light", "fatigue",
                     "cannot create energy", ("create_matter", "resurrection", "rewrite_history")),)
    religions = tuple(Religion(stable_id("religion", seed, i), "ancestors guard remembered roads",
                               "keeper circle", "destroying a waystone", site_id)
                      for i, site_id in enumerate(site_ids[:max(1, min(4, len(site_ids)))])
    )
    return laws, religions
