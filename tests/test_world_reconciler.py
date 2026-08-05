from dataclasses import replace

from src.validators.world_reconciler import WorldReconciler
from src.world.builder import deterministic_candidate
from src.world.models import LocalEntity
from src.world.views import WorldView


def test_valid_candidate_reconciles(phase4_world):
    view = WorldView(phase4_world)
    report = WorldReconciler().reconcile(view, deterministic_candidate(view, "Ash", "", 1))
    assert report.accepted and not report.issues
    assert report.world_artifact_ids == view.artifact_ids
    assert report.world_file_hashes == view.file_hashes


def test_precise_geography_government_chronology_and_container_issues(phase4_world):
    view = WorldView(phase4_world)
    candidate = deterministic_candidate(view, "Ash", "", 1)
    bad_region = replace(candidate.regions[0], climate_regime=999, biome_id=999,
                         resources=("impossible",), neighbors=("region_unknown",))
    bad_civ = replace(candidate.civilizations[0], government="impossible", territory=("region_unknown",))
    bad_event = replace(candidate.history[0], year=9999, causes=("event_unknown",))
    bad_local = LocalEntity("local_bad", "ruin", "Bad Ruin", "region_unknown", ("unknown",))
    bad = replace(candidate, regions=(bad_region,) + candidate.regions[1:],
                  civilizations=(bad_civ,) + candidate.civilizations[1:],
                  history=(bad_event,) + candidate.history[1:], local_entities=(bad_local,))
    report = WorldReconciler().reconcile(view, bad)
    codes = {issue.code for issue in report.issues}
    assert {"WORLD-CLIMATE", "WORLD-BIOME", "WORLD-RESOURCE", "WORLD-ADJACENCY",
            "WORLD-GOVERNMENT", "WORLD-TERRITORY", "WORLD-CHRONOLOGY", "WORLD-CAUSALITY",
            "WORLD-CONTAINER", "WORLD-LOCAL-REF"} <= codes
    assert not report.accepted
    assert all(issue.path.startswith("/") for issue in report.issues)


def test_unknown_identity_route_and_magic_belief_rejected(phase4_world):
    view = WorldView(phase4_world)
    candidate = deterministic_candidate(view, "Ash", "", 1)
    bad_route = replace(candidate.routes[0], end_region="region_unknown")
    bad_magic = replace(candidate.magic_claims[0], statement="creates matter freely")
    report = WorldReconciler().reconcile(view, replace(candidate,
        routes=(bad_route,) + candidate.routes[1:], magic_claims=(bad_magic,) + candidate.magic_claims[1:]))
    assert {"WORLD-ROUTE", "WORLD-MAGIC-CONTRADICTION"} <= {issue.code for issue in report.issues}


def test_semantic_critic_cannot_override_deterministic_failure(phase4_world):
    view = WorldView(phase4_world)
    candidate = replace(deterministic_candidate(view, "Ash", "", 1), present_year=-1)
    report = WorldReconciler().reconcile(view, candidate, critic_issues=(), critic_status="completed")
    assert not report.accepted
    assert any(issue.code == "WORLD-PRESENT-YEAR" for issue in report.issues)
