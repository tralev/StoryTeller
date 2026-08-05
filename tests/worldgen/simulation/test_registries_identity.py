from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.registries import validate_and_hash_registries


def test_registries_and_identities_are_retained(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    assert repository.load_verified("registries").payload == validate_and_hash_registries()
    identities = repository.load_verified("identities").payload
    assert identities["languages"] and identities["heraldry"]
    assert identities["magic_laws"] and identities["religions"]
    assert all("create_matter" in law["prohibited_effects"] for law in identities["magic_laws"])
