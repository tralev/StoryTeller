from dataclasses import replace

import pytest

from src.world.art_direction import derive_art_direction
from src.world.builder import deterministic_candidate
from src.world.views import WorldView


def test_art_direction_uses_maps_climate_cultures_and_bible_refs(phase4_world):
    view = WorldView(phase4_world)
    bible = deterministic_candidate(view, "Ash", "", 1)
    style = derive_art_direction(view, bible)
    assert style.world_map.endswith("world.png")
    assert style.climate_palettes and style.culture_motifs
    assert style.accepted_bible_refs == bible.authoritative_refs


def test_art_direction_rejects_bible_for_other_world(phase4_world):
    view = WorldView(phase4_world)
    bible = replace(deterministic_candidate(view, "Ash", "", 1), authoritative_refs=())
    with pytest.raises(ValueError):
        derive_art_direction(view, bible)
