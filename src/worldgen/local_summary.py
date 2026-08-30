"""Typed non-additive micro-to-macro accounting summaries for local sites."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, cast

from .numeric import identity, stable_id

if TYPE_CHECKING:
    from .local_maps import LocalSiteMap


SUMMARY_RULES = (
    ("population", "macro_reference;local_entities_zero_weight"),
    ("production", "macro_workshop_identity;local_voxels_nonadditive"),
    ("storage", "macro_inventory_reference"),
    ("resources", "macro_deposit_identity;local_voxels_nonextractive"),
    ("routes", "macro_route_identity;local_edges_nonadditive"),
    ("damage", "macro_status_with_local_debris_refinement"),
    ("ownership", "macro_civilization_reference"),
)


@dataclass(frozen=True)
class LocalMacroSummary:
    algorithm_version: int
    summary_id: str
    site_id: str
    settlement_id: str
    population: int
    local_entity_anchor_count: int
    workshop_ids: tuple[str, ...]
    local_workshop_voxels: int
    storage: tuple[tuple[str, int], ...]
    deposit_ids: tuple[str, ...]
    local_deposit_voxels: int
    route_ids: tuple[str, ...]
    local_route_voxels: int
    settlement_status: str
    local_debris_mass: int
    civilization_id: str
    aggregation_rules: tuple[tuple[str, str], ...]
    source_ids: tuple[str, ...]


def derive_local_macro_summary(local: LocalSiteMap) -> LocalMacroSummary:
    """Project local refinements while retaining macro quantities by reference."""
    boundary = local.boundary
    if boundary is None or local.structural_simulation is None:
        raise ValueError("WG-LOCAL-SUMMARY-DERIVE: incomplete local authority")
    features = tuple(local.features)

    def voxel_count(kind: str) -> int:
        return sum(len(feature.cells) for feature in features if feature.kind == kind)

    route_voxels = sum(
        len(feature.cells) for feature in features if feature.kind == "route_connection"
    )
    debris_mass = sum(item.mass for item in local.structural_simulation.final.debris)
    return LocalMacroSummary(
        1,
        stable_id(
            "local_macro_summary",
            boundary.macro_cell,
            identity("boundary", boundary.boundary_id),
            identity("site", local.site_id),
        ),
        local.site_id,
        boundary.settlement_id,
        boundary.settlement_population,
        len(local.entities),
        boundary.workshop_ids,
        voxel_count("workshop"),
        boundary.inventory,
        boundary.deposit_ids,
        voxel_count("mineral_deposit"),
        boundary.route_ids,
        route_voxels,
        boundary.settlement_status,
        debris_mass,
        boundary.civilization_id,
        SUMMARY_RULES,
        boundary.source_artifact_ids,
    )


def validate_local_macro_summary(local: LocalSiteMap, summary: LocalMacroSummary) -> None:
    """Reject additive local accounts or summaries that contradict macro authority."""
    if summary != derive_local_macro_summary(local):
        raise ValueError("WG-LOCAL-SUMMARY-RECONCILE: summary contradicts local/macro authority")
    if (
        summary.algorithm_version != 1
        or summary.aggregation_rules != SUMMARY_RULES
        or summary.workshop_ids != tuple(sorted(set(summary.workshop_ids)))
        or summary.storage != tuple(sorted(summary.storage))
        or summary.deposit_ids != tuple(sorted(set(summary.deposit_ids)))
        or summary.route_ids != tuple(sorted(set(summary.route_ids)))
        or min(
            summary.population,
            summary.local_entity_anchor_count,
            summary.local_workshop_voxels,
            summary.local_deposit_voxels,
            summary.local_route_voxels,
            summary.local_debris_mass,
        )
        < 0
    ):
        raise ValueError("WG-LOCAL-SUMMARY-SHAPE: noncanonical accounting summary")


def local_macro_summary_from_mapping(value: Mapping[str, object]) -> LocalMacroSummary:
    """Strictly decode a persisted local-to-macro summary."""
    if set(value) != {field.name for field in fields(LocalMacroSummary)}:
        raise ValueError("WG-LOCAL-SUMMARY-READ: field set mismatch")

    def integer(name: str) -> int:
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-SUMMARY-READ: {name} must be an integer")
        return item

    def text(name: str) -> str:
        item = value[name]
        if not isinstance(item, str) or not item:
            raise ValueError(f"WG-LOCAL-SUMMARY-READ: {name} must be text")
        return item

    def strings(name: str) -> tuple[str, ...]:
        raw = value[name]
        if (
            not isinstance(raw, Sequence)
            or isinstance(raw, (str, bytes))
            or any(not isinstance(item, str) for item in raw)
        ):
            raise ValueError(f"WG-LOCAL-SUMMARY-READ: invalid {name}")
        return tuple(raw)

    def pairs(name: str, second_type: type[int] | type[str]) -> tuple[tuple[str, object], ...]:
        raw = value[name]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError(f"WG-LOCAL-SUMMARY-READ: invalid {name}")
        result: list[tuple[str, object]] = []
        for pair in raw:
            if (
                not isinstance(pair, Sequence)
                or isinstance(pair, (str, bytes))
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or isinstance(pair[1], bool)
                or not isinstance(pair[1], second_type)
            ):
                raise ValueError(f"WG-LOCAL-SUMMARY-READ: invalid {name} entry")
            result.append((pair[0], pair[1]))
        return tuple(result)

    storage = pairs("storage", int)
    rules = pairs("aggregation_rules", str)
    summary = LocalMacroSummary(
        integer("algorithm_version"),
        text("summary_id"),
        text("site_id"),
        text("settlement_id"),
        integer("population"),
        integer("local_entity_anchor_count"),
        strings("workshop_ids"),
        integer("local_workshop_voxels"),
        tuple((key, cast(int, amount)) for key, amount in storage),
        strings("deposit_ids"),
        integer("local_deposit_voxels"),
        strings("route_ids"),
        integer("local_route_voxels"),
        text("settlement_status"),
        integer("local_debris_mass"),
        text("civilization_id"),
        tuple((key, str(rule)) for key, rule in rules),
        strings("source_ids"),
    )
    if summary.aggregation_rules != SUMMARY_RULES or summary.source_ids != tuple(
        dict.fromkeys(summary.source_ids)
    ):
        raise ValueError("WG-LOCAL-SUMMARY-READ: noncanonical rules or sources")
    return summary
