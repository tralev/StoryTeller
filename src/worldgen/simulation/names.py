"""Entity-local deterministic languages, names, scripts, flags, and heraldry."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import rng_for, stable_id

ONSETS = ("k", "m", "n", "r", "s", "th", "v", "z")
VOWELS = ("a", "e", "i", "o", "u", "ae")
CODAS = ("", "n", "r", "s", "th")
COLORS = ("ashen", "crimson", "golden", "iron", "verdant", "silver")
SYMBOLS = ("tower", "crown", "river", "star", "wolf", "oak")


@dataclass(frozen=True)
class LanguageIdentity:
    language_id: str
    name: str
    script: str
    morphemes: tuple[str, ...]


def generate_identity(seed: int, entity_index: int, used: set[str]) -> tuple[str, LanguageIdentity, str]:
    rng = rng_for(seed, "civilization.identity", entity_index)
    morphemes = tuple(ONSETS[rng.below(len(ONSETS))] + VOWELS[rng.below(len(VOWELS))]
                      + CODAS[rng.below(len(CODAS))] for _ in range(8))
    for rejection in range(100):
        name = (morphemes[(2 * rejection) % len(morphemes)]
                + morphemes[(2 * rejection + 1) % len(morphemes)]).title()
        if name not in used:
            used.add(name)
            break
    else:
        name = f"People {entity_index + 1}"
    language = LanguageIdentity(stable_id("language", seed, entity_index), f"{name}ic",
                                ("runes", "glyphs", "knots")[rng.below(3)], morphemes)
    heraldry = f"{COLORS[rng.below(len(COLORS))]} {SYMBOLS[rng.below(len(SYMBOLS))]}"
    return name, language, heraldry
