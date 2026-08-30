from copy import deepcopy
from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.cosmology import generate_cosmology, validate_cosmology
from src.worldgen.simulation.heraldry import (
    MIN_LUMINANCE_DIFFERENCE_PPM,
    generate_heraldry,
    validate_heraldry,
)
from src.worldgen.simulation.language_evolution import (
    evolve_language,
    name_skeleton,
    realize_syllable,
    validate_name,
)
from src.worldgen.simulation.magic import (
    EpistemicStatus,
    MagicEffect,
    generate_supernatural,
    validate_supernatural,
)
from src.worldgen.simulation.names import CulturePressure, generate_identity
from src.worldgen.simulation.registries import (
    SIMULATION_REGISTRIES,
    SIMULATION_STAGE_REGISTRIES,
    simulation_stage_fingerprint,
    validate_and_hash_registries,
)


def test_registries_and_identities_are_retained(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    assert repository.load_verified("registries").payload == validate_and_hash_registries()
    identities = repository.load_verified("identities").payload
    assert identities["languages"] and identities["heraldry"] and identities["flags"]
    assert all(design["motif"]["meaning_source_id"] for design in identities["heraldry"].values())
    assert all(language["environment_signature"] for language in identities["languages"])
    assert identities["language_history"]
    assert identities["magic_laws"] and identities["magic_effects"] and identities["religions"]
    assert all("create_matter" in law["prohibited_effects"] for law in identities["magic_laws"])
    law_ids = {law["law_id"] for law in identities["magic_laws"]}
    assert all(
        effect["law_id"] in law_ids and effect["source_id"]
        for effect in identities["magic_effects"]
    )
    assert all(
        religion["attributed_to"] and religion["epistemic_status"] == "uncertain"
        for religion in identities["religions"]
    )
    assert identities["cosmological_layers"] and identities["celestial_cycles"]
    assert identities["cosmological_entities"] and identities["afterlife_claims"]
    assert identities["supernatural_places"] and identities["cults"] and identities["sacred_relics"]


def test_society_registries_are_complete_versioned_unique_and_stable():
    hashes = validate_and_hash_registries()
    assert set(hashes) == {
        "people",
        "technologies",
        "occupations",
        "materials",
        "recipes",
        "institutions",
        "governments",
        "beliefs",
        "magic_vocabulary",
        "language",
        "species",
    }
    assert all(
        registry["version"] == 1 and registry["entries"]
        for registry in SIMULATION_REGISTRIES.values()
    )
    assert hashes == validate_and_hash_registries()


@pytest.mark.parametrize(
    ("registry", "direct_producers"),
    (
        (
            "governments",
            {
                "civilizations",
                "government_reforms",
                "history",
                "history_clock",
                "registries",
                "simulation_index",
                "snapshots",
                "successions",
            },
        ),
        (
            "materials",
            {
                "construction_projects",
                "economy",
                "history",
                "history_clock",
                "legendary_artifacts",
                "registries",
                "settlements",
                "simulation_index",
                "snapshots",
            },
        ),
        (
            "beliefs",
            {
                "history",
                "history_clock",
                "identities",
                "registries",
                "religious_patronage",
                "religious_schisms",
                "simulation_index",
                "snapshots",
            },
        ),
        (
            "language",
            {
                "history",
                "history_clock",
                "identities",
                "registries",
                "simulation_index",
                "snapshots",
            },
        ),
    ),
)
def test_registry_changes_invalidate_only_declared_simulation_producers(registry, direct_producers):
    original = validate_and_hash_registries()
    changed = dict(original)
    changed[registry] = "f" * 64 if original[registry] != "f" * 64 else "e" * 64
    differences = {
        stage
        for stage in SIMULATION_STAGE_REGISTRIES
        if simulation_stage_fingerprint(stage, 20, original)
        != simulation_stage_fingerprint(stage, 20, changed)
    }
    assert differences == direct_producers


def test_society_registry_validator_rejects_set_version_and_identity_defects():
    missing = deepcopy(SIMULATION_REGISTRIES)
    missing.pop("beliefs")
    with pytest.raises(ValueError, match="REGISTRY-SET"):
        validate_and_hash_registries(missing)
    unversioned = deepcopy(SIMULATION_REGISTRIES)
    unversioned["language"]["version"] = 0
    with pytest.raises(ValueError, match="REGISTRY-VERSION"):
        validate_and_hash_registries(unversioned)
    duplicate = deepcopy(SIMULATION_REGISTRIES)
    duplicate["occupations"]["entries"] = ({"id": "same"}, {"id": "same"})
    with pytest.raises(ValueError, match="REGISTRY-DUPLICATE"):
        validate_and_hash_registries(duplicate)


def test_cultural_identity_is_stable_and_registry_driven():
    pressure = CulturePressure(6, 2, True, 3, ("iron", "timber"))
    first = generate_identity(91, "site-founder-1", set(), pressure)
    second = generate_identity(91, "site-founder-1", set(), pressure)
    style = next(
        entry
        for entry in SIMULATION_REGISTRIES["language"]["entries"]
        if entry["id"] == "identity_style_v1"
    )
    phonemes = next(
        entry
        for entry in SIMULATION_REGISTRIES["language"]["entries"]
        if entry["id"] == "phonemes_v1"
    )

    assert first == second
    assert first.language.script in style["scripts"]
    assert len(first.language.morphemes) == 8
    assert first.language.syllable_pattern in {"CV", "CVC", "VC"}
    if first.language.syllable_pattern.startswith("C"):
        assert all(
            any(morpheme.startswith(onset) for onset in phonemes["onsets"])
            for morpheme in first.language.morphemes
        )
    else:
        assert all(
            any(morpheme.startswith(vowel) for vowel in phonemes["vowels"])
            for morpheme in first.language.morphemes
        )
    assert first.language.environment_signature == pressure.signature
    assert "waterside navigation" in first.culture_traits
    assert "crossroads exchange" in first.culture_traits


def test_environment_changes_expression_but_not_founder_language_identity():
    dry_isolated = CulturePressure(4, 4, False, 0, ())
    wet_connected = CulturePressure(8, 1, True, 4, ("grain",))
    dry = generate_identity(19, "same-founder", set(), dry_isolated)
    wet = generate_identity(19, "same-founder", set(), wet_connected)

    assert dry.language.language_id == wet.language.language_id
    assert dry.language.environment_signature != wet.language.environment_signature
    assert (
        dry.language.morphemes,
        dry.language.script,
        dry.flag,
        dry.heraldry,
        dry.culture_traits,
    ) != (wet.language.morphemes, wet.language.script, wet.flag, wet.heraldry, wet.culture_traits)
    assert "waterside navigation" not in dry.culture_traits
    assert "waterside navigation" in wet.culture_traits


def test_vector_heraldry_is_deterministic_contrasting_and_culturally_cited():
    traits = ("crossroads exchange", "waterside navigation")
    first = generate_heraldry(91, "founder-a", traits, "culture-source-a")
    second = generate_heraldry(91, "founder-a", traits, "culture-source-a")
    assert first == second
    assert first.aspect_width == 3 and first.aspect_height == 2
    assert (
        abs(first.primary.luminance_ppm - first.secondary.luminance_ppm)
        >= MIN_LUMINANCE_DIFFERENCE_PPM
    )
    assert 0 <= first.motif.center_x_ppm <= 1_000_000
    assert 0 <= first.motif.center_y_ppm <= 1_000_000
    assert first.motif.meaning_source_kind == "culture_trait"
    assert first.motif.meaning_source_id == "culture-source-a"
    assert any(trait in first.motif.meaning for trait in traits)
    validate_heraldry(first)


def test_heraldry_validator_rejects_low_contrast_uncited_and_invalid_vectors():
    design = generate_heraldry(37, "founder-b", ("stonecraft",), "culture-source-b")
    with pytest.raises(ValueError, match="HERALDRY-CONTRAST"):
        validate_heraldry(replace(design, secondary=design.primary))
    with pytest.raises(ValueError, match="HERALDRY-CITATION"):
        validate_heraldry(
            replace(
                design,
                motif=replace(design.motif, meaning_source_id=""),
            )
        )
    with pytest.raises(ValueError, match="HERALDRY-VECTOR"):
        validate_heraldry(
            replace(
                design,
                motif=replace(design.motif, center_x_ppm=1_000_001),
            )
        )
    with pytest.raises(ValueError, match="HERALDRY-COLOR"):
        validate_heraldry(
            replace(
                design,
                primary=replace(design.primary, hex_rgb="#FFFFFF"),
            )
        )


def test_cultural_pressure_rejects_order_dependent_resources():
    with pytest.raises(ValueError, match="unique and sorted"):
        CulturePressure(5, 2, False, 1, ("timber", "iron"))


def test_objective_magic_effects_cite_law_and_registry_source():
    laws, sources, effects, religions, institutions, schisms, interpretations = (
        generate_supernatural(37, ("site-a", "site-b"))
    )
    assert effects and effects[0].law_id == laws[0].law_id
    assert effects[0].source_id == sources[0].source_id
    assert sources[0].vocabulary_id == "resonance"
    assert effects[0].paid_cost == laws[0].cost
    assert all(
        religion.attributed_to == "keeper_circle"
        and religion.epistemic_status is EpistemicStatus.UNCERTAIN
        for religion in religions
    )
    validate_supernatural(laws, sources, effects, religions, institutions, schisms, interpretations)


def test_cosmology_is_layered_attributed_cyclical_and_place_bound():
    supernatural = generate_supernatural(37, ("site-a", "site-b", "site-c"))
    bundle = generate_cosmology(
        37,
        supernatural.laws,
        supernatural.sources,
        supernatural.religions,
        ("site-a", "site-b", "site-c"),
    )
    assert tuple(layer.order for layer in bundle.layers) == (0, 1, 2)
    assert all(cycle.period_months > cycle.phase_offset_months >= 0 for cycle in bundle.cycles)
    assert {entity.entity_kind for entity in bundle.entities} == {
        "deity",
        "spirit",
        "demon",
        "saint",
        "false_entity",
    }
    assert all(
        entity.attributed_to and entity.epistemic_status is not EpistemicStatus.TRUE
        for entity in bundle.entities
    )
    assert all(
        claim.attributed_to and claim.destination_layer_id for claim in bundle.afterlife_claims
    )
    assert {place.site_id for place in bundle.places} == {"site-a", "site-b", "site-c"}
    assert {place.phenomenon_kind for place in bundle.places} == {"hazard", "resource"}
    assert all(cult.rite and cult.site_id for cult in bundle.cults)
    assert all(relic.attributed_power and relic.attributed_to for relic in bundle.relics)
    validate_cosmology(
        bundle,
        supernatural.laws,
        supernatural.sources,
        supernatural.religions,
        ("site-a", "site-b", "site-c"),
    )
    assert bundle == generate_cosmology(
        37,
        supernatural.laws,
        supernatural.sources,
        supernatural.religions,
        ("site-a", "site-b", "site-c"),
    )


def test_cosmology_validator_rejects_uncited_claims_and_forged_place_links():
    supernatural = generate_supernatural(41, ("site-a", "site-b"))
    bundle = generate_cosmology(
        41,
        supernatural.laws,
        supernatural.sources,
        supernatural.religions,
        ("site-a", "site-b"),
    )
    with pytest.raises(ValueError, match="COSMOLOGY-ATTRIBUTION"):
        validate_cosmology(
            bundle._replace(
                entities=(replace(bundle.entities[0], attributed_to=""), *bundle.entities[1:])
            ),
            supernatural.laws,
            supernatural.sources,
            supernatural.religions,
            ("site-a", "site-b"),
        )
    with pytest.raises(ValueError, match="COSMOLOGY-PLACE"):
        validate_cosmology(
            bundle._replace(
                places=(replace(bundle.places[0], source_id="forged"), *bundle.places[1:])
            ),
            supernatural.laws,
            supernatural.sources,
            supernatural.religions,
            ("site-a", "site-b"),
        )


def test_magic_validator_rejects_uncited_or_law_inconsistent_effect():
    laws, sources, effects, religions, institutions, schisms, interpretations = (
        generate_supernatural(38, ("site-a",))
    )
    effect = effects[0]
    uncited = MagicEffect(
        effect.effect_id,
        "missing-law",
        effect.source_id,
        effect.effect,
        effect.paid_cost,
        effect.side_effect,
        effect.location_id,
    )
    with pytest.raises(ValueError, match="EFFECT-SOURCE"):
        validate_supernatural(
            laws, sources, (uncited,), religions, institutions, schisms, interpretations
        )
    unpaid = MagicEffect(
        effect.effect_id,
        effect.law_id,
        effect.source_id,
        effect.effect,
        "nothing",
        effect.side_effect,
        effect.location_id,
    )
    with pytest.raises(ValueError, match="EFFECT-LAW"):
        validate_supernatural(
            laws, sources, (unpaid,), religions, institutions, schisms, interpretations
        )


def test_magic_sources_institutions_schisms_and_interpretations_are_place_bound():
    (laws, sources, effects, religions, institutions, schisms, interpretations) = (
        generate_supernatural(41, ("site-a", "site-b", "site-c"))
    )
    assert {source.location_id for source in sources} == {"site-a", "site-b", "site-c"}
    assert all(source.law_id == laws[0].law_id for source in sources)
    assert effects[0].side_effect == "temporary color blindness"
    assert {institution.site_id for institution in institutions} == {
        religion.holy_site_id for religion in religions
    }
    assert len(schisms) == len(religions) - 1
    assert all(schism.parent_religion_id == religions[0].religion_id for schism in schisms)
    assert all(
        interpretation.epistemic_status is EpistemicStatus.METAPHORICAL
        and interpretation.law_id == laws[0].law_id
        for interpretation in interpretations
    )
    assert generate_supernatural(41, ("site-a", "site-b", "site-c")) == (
        laws,
        sources,
        effects,
        religions,
        institutions,
        schisms,
        interpretations,
    )


@pytest.mark.parametrize(
    ("pattern", "expected"),
    (
        ("CV", "ka"),
        ("CVC", "kan"),
        ("VC", "an"),
    ),
)
def test_syllable_patterns_have_exact_realization(pattern, expected):
    assert realize_syllable(pattern, "k", "a", "n") == expected
    with pytest.raises(ValueError, match="LANGUAGE-PATTERN"):
        realize_syllable("CVV", "k", "a", "n")


def test_name_safety_rejects_reserved_prohibited_duplicate_and_confusable_forms():
    with pytest.raises(ValueError, match="NAME-RESERVED"):
        validate_name("Admin", set())
    with pytest.raises(ValueError, match="NAME-PROHIBITED"):
        validate_name("Damnor", set())
    with pytest.raises(ValueError, match="NAME-DUPLICATE"):
        validate_name("Moral", {"Moral"})
    assert name_skeleton("L0r1") == name_skeleton("iori")
    with pytest.raises(ValueError, match="NAME-DUPLICATE"):
        validate_name("L0r1", {"iori"})


def test_language_sound_changes_are_historical_stable_and_keep_language_id():
    identity_design = generate_identity(
        91,
        "founder-language",
        set(),
        CulturePressure(6, 2, True, 2, ("timber",)),
    )
    language = identity_design.language
    stages = evolve_language(language.language_id, ("thaen", "vath"), 100)
    assert tuple(stage.year for stage in stages) == (0, 25, 50, 100)
    assert all(stage.language_id == language.language_id for stage in stages)
    assert stages[0].morphemes == ("thaen", "vath")
    assert stages[-1].morphemes == ("ten", "fat")
    assert stages == evolve_language(language.language_id, ("thaen", "vath"), 100)


def test_persisted_language_history_reaches_configured_year(simulated_world):
    _, historical, _ = simulated_world
    identities = (
        WorldArtifactRepository(historical / "artifacts").load_verified("identities").payload
    )
    stages_by_language = {}
    for stage in identities["language_history"]:
        stages_by_language.setdefault(stage["language_id"], []).append(stage)
    assert set(stages_by_language) == {
        language["language_id"] for language in identities["languages"]
    }
    assert all(
        [stage["year"] for stage in stages] == [0, 25, 50] for stages in stages_by_language.values()
    )
