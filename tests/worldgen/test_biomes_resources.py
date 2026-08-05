def test_biomes_cover_all_cells_and_resources_are_compatible(physical_world):
    terrain, _, _, biomes, resources, *_ = physical_world
    assert len(biomes.biome_id.values) == terrain.grid.cell_count
    assert all(0 <= biome <= 8 for biome in biomes.biome_id.values)
    assert all(all(terrain.land.values[cell] for cell in deposit.cells) for deposit in resources.deposits)
    assert all(deposit.quantity_kg > 0 and 0 < deposit.grade_ppm <= 1_000_000
               for deposit in resources.deposits)
    assert len(resources.strata_id.values) == terrain.grid.cell_count
    assert len(resources.parent_material_id.values) == terrain.grid.cell_count


def test_food_web_energy_bounds_and_migration(physical_world):
    _, _, _, biomes, _, regions, _ = physical_world
    ecology = generate_ecology(biomes, regions, 42)
    energy = {species.species_id: species.annual_energy_kj for species in ecology.species}
    assert all(edge.transferred_energy_kj <= energy[edge.predator]
               and edge.transferred_energy_kj <= energy[edge.prey] // 10
               for edge in ecology.food_web)
from src.worldgen.ecology import generate_ecology
