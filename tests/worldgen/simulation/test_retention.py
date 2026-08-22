import hashlib
from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository, canonical_json
from src.worldgen.simulation.replay import _state
from src.worldgen.simulation.retention import build_retention_inventory
from src.worldgen.simulation.snapshots import make_snapshot
from src.worldgen.simulation.state import SettlementStatus


def test_retention_inventory_covers_complete_authoritative_artifacts(simulated_world) -> None:
    _, historical, result = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    inventory = repository.load_verified("retention_inventory").payload
    history = repository.load_verified("history").payload
    snapshots = repository.load_verified("snapshots").payload
    registries = repository.load_verified("registries").payload

    assert inventory["event_count"] == result["events"] == len(history)
    assert tuple(inventory["event_ids"]) == tuple(item["event_id"] for item in history)
    assert tuple(inventory["snapshot_years"]) == tuple(item["year"] for item in snapshots)
    assert inventory["ledger_sha256"] == hashlib.sha256(canonical_json(history)).hexdigest()
    assert inventory["snapshots_sha256"] == hashlib.sha256(
        canonical_json(snapshots)
    ).hexdigest()
    assert inventory["registries_sha256"] == hashlib.sha256(
        canonical_json(registries)
    ).hexdigest()
    assert inventory["identity_ids"]
    assert inventory["unreferenced_identity_ids"]
    assert inventory["dead_megabeast_ids"]
    created_artifact_ids = {
        consequence["subject"]
        for event in history for consequence in event["consequences"]
        if consequence["kind"] == "artifact_create"
    }
    assert created_artifact_ids <= set(inventory["identity_ids"])


def test_extinct_and_abandoned_entities_are_retained_and_discard_is_rejected(
    simulated_world,
) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    genesis = _state(repository.load_verified("snapshots").payload[0]["state"])
    civilization = genesis.civilizations[0]
    settlement = next(item for item in genesis.settlements
                      if item.civilization_id == civilization.civilization_id)
    final = replace(
        genesis,
        civilizations=tuple(replace(item, active=False)
                            if item == civilization else item
                            for item in genesis.civilizations),
        settlements=tuple(replace(item, status=SettlementStatus.ABANDONED,
                                  abandoned_year=1)
                          if item == settlement else item
                          for item in genesis.settlements),
    )
    identity_ids = tuple(sorted(
        {item.civilization_id for item in genesis.civilizations}
        | {item.settlement_id for item in genesis.settlements}
        | {item.site_id for item in genesis.sites}
    ))
    inventory = build_retention_inventory(
        (), (make_snapshot(genesis), make_snapshot(final)), {}, identity_ids,
        genesis, final,
    )

    assert inventory.extinct_civilization_ids == (civilization.civilization_id,)
    assert inventory.abandoned_settlement_ids == (settlement.settlement_id,)
    with pytest.raises(ValueError, match="WG-HISTORY-RETENTION"):
        build_retention_inventory(
            (), (make_snapshot(genesis),), {}, identity_ids, genesis,
            replace(genesis, civilizations=genesis.civilizations[1:]),
        )
