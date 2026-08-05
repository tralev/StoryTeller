"""Deterministic reconciliation of Bible enrichment against world facts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..world.models import BibleV2
from ..world.views import WorldView


@dataclass(frozen=True)
class ReconciliationIssue:
    code: str
    path: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ReconciliationReport:
    accepted: bool
    world_artifact_ids: dict[str, str]
    world_file_hashes: dict[str, str]
    ruleset_version: int
    issues: tuple[ReconciliationIssue, ...]
    critic_status: str = "not_requested"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def retry_feedback(self) -> str:
        return "\n".join(f"{issue.code} {issue.path}: {issue.message}"
                         for issue in sorted(self.issues, key=lambda item: (item.path, item.code)))


class WorldReconciler:
    RULESET_VERSION = 1

    def reconcile(self, world: WorldView, bible: BibleV2, *, critic_issues: Iterable[str] = (),
                  critic_status: str = "not_requested") -> ReconciliationReport:
        issues: list[ReconciliationIssue] = []
        expected_refs = set(world.artifact_ids.values())
        if set(bible.authoritative_refs) != expected_refs:
            issues.append(ReconciliationIssue("WORLD-REFS", "/authoritative_refs",
                                               "must exactly reference every checked world artifact"))
        if bible.present_year != world.present_year:
            issues.append(ReconciliationIssue("WORLD-PRESENT-YEAR", "/present_year",
                                               f"expected {world.present_year}"))
        region_facts = {fact.fact_id: fact.value for fact in world.regions()}
        region_claims = {claim.region_id: claim for claim in bible.regions}
        if set(region_claims) != set(region_facts):
            issues.append(ReconciliationIssue("WORLD-REGION-COVERAGE", "/regions",
                                               "all authoritative regions must be addressed"))
        for index, claim in enumerate(bible.regions):
            path = f"/regions/{index}"
            fact = region_facts.get(claim.region_id)
            if fact is None:
                issues.append(ReconciliationIssue("WORLD-REGION-UNKNOWN", path + "/region_id", claim.region_id)); continue
            checks = (("center", claim.center, fact["center"], "WORLD-COORDINATE"),
                      ("biome_id", claim.biome_id, fact["biome_id"], "WORLD-BIOME"),
                      ("climate_regime", claim.climate_regime, fact["climate_regime"], "WORLD-CLIMATE"),
                      ("resources", tuple(claim.resources), tuple(fact["resources"]), "WORLD-RESOURCE"),
                      ("neighbors", tuple(claim.neighbors), tuple(fact["neighbors"]), "WORLD-ADJACENCY"))
            for field, actual, expected, code in checks:
                if actual != expected:
                    issues.append(ReconciliationIssue(code, f"{path}/{field}", f"expected {expected!r}"))
        route_facts = {fact.fact_id: fact.value for fact in world.routes()}
        if {claim.route_id for claim in bible.routes} != set(route_facts):
            issues.append(ReconciliationIssue("WORLD-ROUTE-COVERAGE", "/routes",
                                               "all authoritative routes must be addressed"))
        for index, route_claim in enumerate(bible.routes):
            fact = route_facts.get(route_claim.route_id)
            if fact is None or (route_claim.start_region, route_claim.end_region) != (fact["start_region"], fact["end_region"]):
                issues.append(ReconciliationIssue("WORLD-ROUTE", f"/routes/{index}", "unknown or impossible route"))
        civilization_facts = {fact.fact_id: fact.value for fact in world.civilizations()}
        claimed_civilizations = {claim.civilization_id for claim in bible.civilizations}
        if claimed_civilizations != set(civilization_facts):
            issues.append(ReconciliationIssue("WORLD-CIV-COVERAGE", "/civilizations",
                                               "all authoritative civilizations must be addressed"))
        for index, civilization_claim in enumerate(bible.civilizations):
            fact = civilization_facts.get(civilization_claim.civilization_id)
            if fact is None:
                issues.append(ReconciliationIssue("WORLD-CIV-UNKNOWN", f"/civilizations/{index}", civilization_claim.civilization_id)); continue
            if civilization_claim.government != fact["government"]:
                issues.append(ReconciliationIssue("WORLD-GOVERNMENT", f"/civilizations/{index}/government",
                                                   f"expected {fact['government']}"))
            if tuple(civilization_claim.territory) != tuple(fact["territory"]):
                issues.append(ReconciliationIssue("WORLD-TERRITORY", f"/civilizations/{index}/territory",
                                                   "territory contradicts present state"))
        event_facts = {fact.fact_id: fact.value for fact in world.events()}
        for index, event_claim in enumerate(bible.history):
            fact = event_facts.get(event_claim.event_id)
            if fact is None:
                issues.append(ReconciliationIssue("WORLD-EVENT-UNKNOWN", f"/history/{index}", event_claim.event_id)); continue
            if event_claim.year != fact["year"]:
                issues.append(ReconciliationIssue("WORLD-CHRONOLOGY", f"/history/{index}/year",
                                                   f"expected {fact['year']}"))
            if tuple(event_claim.causes) != tuple(fact["causes"]):
                issues.append(ReconciliationIssue("WORLD-CAUSALITY", f"/history/{index}/causes",
                                                   "event causes contradict ledger"))
        valid_containers = set(region_facts) | {fact.fact_id for fact in world.sites()} | set(civilization_facts)
        valid_facts = valid_containers | set(event_facts)
        for index, entity in enumerate(bible.local_entities):
            if entity.contained_by not in valid_containers:
                issues.append(ReconciliationIssue("WORLD-CONTAINER", f"/local_entities/{index}/contained_by",
                                                   "local entity must name a valid container"))
            if not entity.authoritative_refs or any(ref not in valid_facts for ref in entity.authoritative_refs):
                issues.append(ReconciliationIssue("WORLD-LOCAL-REF", f"/local_entities/{index}/authoritative_refs",
                                                   "unknown authoritative fact reference"))
        identities = world.identities().value
        laws = {law["law_id"]: law for law in identities["magic_laws"]}
        religions = {religion["religion_id"]: religion for religion in identities["religions"]}
        for index, magic_claim in enumerate(bible.magic_claims):
            if magic_claim.epistemic_status == "objective" and magic_claim.authoritative_ref not in laws:
                issues.append(ReconciliationIssue("WORLD-MAGIC-LAW", f"/magic_claims/{index}",
                                                   "objective claim lacks an objective law"))
            elif magic_claim.epistemic_status == "objective" and magic_claim.statement != laws[magic_claim.authoritative_ref]["effect"]:
                issues.append(ReconciliationIssue("WORLD-MAGIC-CONTRADICTION", f"/magic_claims/{index}/statement",
                                                   "objective effect contradicts its law"))
            if magic_claim.epistemic_status == "belief" and magic_claim.authoritative_ref not in religions:
                issues.append(ReconciliationIssue("WORLD-BELIEF", f"/magic_claims/{index}",
                                                   "belief claim lacks a religion"))
            elif magic_claim.epistemic_status == "belief" and magic_claim.statement != religions[magic_claim.authoritative_ref]["belief_claim"]:
                issues.append(ReconciliationIssue("WORLD-BELIEF-CONTRADICTION", f"/magic_claims/{index}/statement",
                                                   "belief must remain an attributed claim"))
        # Semantic criticism can add warnings, never erase deterministic errors.
        issues.extend(ReconciliationIssue("CRITIC", "/interpretations", issue, "warning")
                      for issue in critic_issues)
        accepted = not any(issue.severity == "error" for issue in issues)
        return ReconciliationReport(accepted, world.artifact_ids, world.file_hashes,
                                    self.RULESET_VERSION, tuple(issues), critic_status)
