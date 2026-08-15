"""Settlement lifecycle, land-use, workshop, and inventory validation."""
from __future__ import annotations

from .registries import simulation_registry_entries
from .state import SettlementState, SettlementStatus


def validate_settlements(settlements: tuple[SettlementState, ...]) -> None:
    recipe_ids = {str(recipe["id"]) for recipe in simulation_registry_entries("recipes")}
    settlement_ids = {settlement.settlement_id for settlement in settlements}
    if len(settlement_ids) != len(settlements):
        raise ValueError("WG-SETTLEMENT-ID: duplicate settlement identity")
    for settlement in settlements:
        if not settlement.site_id or settlement.founded_year < 0 or settlement.carrying_capacity < 1:
            raise ValueError(f"WG-SETTLEMENT-FOUNDING: {settlement.settlement_id}")
        if settlement.population < 0 or settlement.population > settlement.carrying_capacity:
            raise ValueError(f"WG-SETTLEMENT-POPULATION: {settlement.settlement_id}")
        if not settlement.land_use or not settlement.buildings:
            raise ValueError(f"WG-SETTLEMENT-LAND-USE: {settlement.settlement_id}")
        if settlement.status is SettlementStatus.ABANDONED and settlement.abandoned_year is None:
            raise ValueError(f"WG-SETTLEMENT-ABANDONMENT: {settlement.settlement_id}")
        if settlement.status is SettlementStatus.INHABITED and settlement.abandoned_year is not None:
            raise ValueError(f"WG-SETTLEMENT-ABANDONMENT: {settlement.settlement_id}")
        workshop_ids = {workshop.workshop_id for workshop in settlement.workshops}
        if len(workshop_ids) != len(settlement.workshops) or any(
                workshop.recipe_id not in recipe_ids or not workshop.input_material
                or not workshop.output_material or not 0 < workshop.ratio_ppm <= 1_000_000
                for workshop in settlement.workshops):
            raise ValueError(f"WG-SETTLEMENT-WORKSHOP: {settlement.settlement_id}")
        materials = [stack.material_id for stack in settlement.inventory]
        if len(materials) != len(set(materials)) or any(stack.quantity < 0
                                                        for stack in settlement.inventory):
            raise ValueError(f"WG-SETTLEMENT-INVENTORY: {settlement.settlement_id}")
