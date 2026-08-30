"""Registry-driven languages, names, flags, heraldry, and environmental culture."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from ..artifacts import canonical_json
from ..numeric import identity, rng_for_decision, stable_id
from .heraldry import VectorHeraldry, generate_heraldry
from .language_evolution import realize_syllable, validate_name
from .registries import simulation_registry_entries


@dataclass(frozen=True)
class CulturePressure:
    biome_id: int
    climate_regime: int
    water_access: bool
    route_degree: int
    resources: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.biome_id, bool)
            or isinstance(self.climate_regime, bool)
            or not isinstance(self.biome_id, int)
            or not isinstance(self.climate_regime, int)
            or self.biome_id < 0
            or self.climate_regime < 0
        ):
            raise ValueError("WG-CULTURE: invalid biome or climate pressure")
        if (
            not isinstance(self.water_access, bool)
            or isinstance(self.route_degree, bool)
            or not isinstance(self.route_degree, int)
            or self.route_degree < 0
        ):
            raise ValueError("WG-CULTURE: invalid water or route pressure")
        if self.resources != tuple(sorted(set(self.resources))):
            raise ValueError("WG-CULTURE: resources must be unique and sorted")

    @property
    def signature(self) -> str:
        return hashlib.sha256(canonical_json(self)).hexdigest()


@dataclass(frozen=True)
class LanguageIdentity:
    language_id: str
    name: str
    script: str
    morphemes: tuple[str, ...]
    syllable_pattern: str
    environment_signature: str


@dataclass(frozen=True)
class CulturalIdentity:
    name: str
    language: LanguageIdentity
    flag: str
    heraldry: VectorHeraldry
    culture_traits: tuple[str, ...]


def _entry(entry_id: str) -> Mapping[str, object]:
    return next(
        entry for entry in simulation_registry_entries("language") if entry["id"] == entry_id
    )


def _strings(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple)
        or not value
        or not all(isinstance(item, str) for item in value)
    ):
        raise ValueError(f"WG-CULTURE: invalid {label} registry")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"WG-CULTURE: invalid {label} registry")
    return value


def generate_identity(
    seed: int, entity_id: str, used: set[str], pressure: CulturePressure
) -> CulturalIdentity:
    phonemes = _entry("phonemes_v1")
    morphology = _entry("morphology_v1")
    style = _entry("identity_style_v1")
    rules = _entry("culture_traits_v1")
    syllable_patterns = _strings(_entry("syllable_patterns_v1")["patterns"], "syllable patterns")
    onsets = _strings(phonemes["onsets"], "onsets")
    vowels = _strings(phonemes["vowels"], "vowels")
    codas = _strings(phonemes["codas"], "codas")
    scripts = _strings(style["scripts"], "scripts")
    colors = _strings(style["colors"], "colors")
    symbols = _strings(style["symbols"], "symbols")
    patterns = _strings(style["patterns"], "patterns")
    rng = rng_for_decision(seed, "civilization.identity", entity_id, pressure.signature)
    count = _positive_int(morphology["morpheme_count"], "morpheme count")
    syllable_pattern = syllable_patterns[rng.below(len(syllable_patterns))]
    morphemes = tuple(
        realize_syllable(
            syllable_pattern,
            onsets[rng.below(len(onsets))],
            vowels[rng.below(len(vowels))],
            codas[rng.below(len(codas))],
        )
        for _ in range(count)
    )
    name_parts = _positive_int(morphology["name_morphemes"], "name morphemes")
    for rejection in range(100):
        name = "".join(
            morphemes[(name_parts * rejection + offset) % len(morphemes)]
            for offset in range(name_parts)
        ).title()
        try:
            validate_name(name, used)
        except ValueError:
            continue
        else:
            used.add(name)
            break
    else:
        name = f"Folk{entity_id[-8:]}"
        validate_name(name, used)
        used.add(name)

    # Rules use environment only. No ancestry, people type, or race input exists.
    script_index = 2 if pressure.water_access else 0 if pressure.biome_id in (1, 2, 3) else 1
    script = scripts[script_index % len(scripts)]
    biome_traits = rules["biome_traits"]
    climate_traits = _strings(rules["climate_traits"], "climate traits")
    if not isinstance(biome_traits, Mapping):
        raise ValueError("WG-CULTURE: invalid biome-trait registry")
    traits = [
        str(biome_traits.get(str(pressure.biome_id), "adaptable mixed subsistence")),
        climate_traits[min(pressure.climate_regime, len(climate_traits) - 1)],
    ]
    if pressure.water_access:
        traits.append(str(rules["water_trait"]))
    if pressure.route_degree:
        traits.append(str(rules["route_trait"]))
    if pressure.resources:
        traits.append(f"{pressure.resources[0]} {rules['resource_trait']}")
    culture_traits = tuple(sorted(set(traits)))

    color = colors[(pressure.climate_regime + rng.below(len(colors))) % len(colors)]
    if pressure.water_access:
        symbol = "river" if "river" in symbols else symbols[0]
    elif pressure.resources:
        symbol = symbols[sum(pressure.resources[0].encode("utf-8")) % len(symbols)]
    else:
        symbol = symbols[(pressure.biome_id + pressure.route_degree) % len(symbols)]
    pattern = patterns[(pressure.route_degree + pressure.biome_id) % len(patterns)]
    language = LanguageIdentity(
        stable_id("language", seed, identity("founder_entity_id", entity_id)),
        f"{name}ic",
        script,
        morphemes,
        syllable_pattern,
        pressure.signature,
    )
    heraldry = generate_heraldry(seed, entity_id, culture_traits, pressure.signature)
    return CulturalIdentity(
        name, language, f"{pattern} {color} field with {symbol}", heraldry, culture_traits
    )
