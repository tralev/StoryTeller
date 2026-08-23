"""Deterministic reconciliation of Bible enrichment against world facts."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from ..world.models import BibleV2
from ..world.projections import ProjectionSet, build_projections, validate_projections
from ..world.views import WorldView
from ..worldgen.artifacts import canonical_json


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
    projection_sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def retry_feedback(self) -> str:
        return "\n".join(
            f"{issue.code} {issue.path}: {issue.message}"
            for issue in sorted(self.issues, key=lambda item: (item.path, item.code))
        )


class WorldReconciler:
    RULESET_VERSION = 2

    def reconcile(
        self,
        world: WorldView,
        bible: BibleV2,
        *,
        projections: ProjectionSet | None = None,
        critic_issues: Iterable[str] = (),
        critic_status: str = "not_requested",
    ) -> ReconciliationReport:
        issues: list[ReconciliationIssue] = []
        projections = projections or build_projections(world)
        validate_projections(projections, world.authoritative_inventory())
        projected = {
            category: {
                record.record_id
                for chunk in projections.chunks
                if chunk.category == category
                for record in chunk.records
            }
            for category in (item.category for item in projections.source_coverage)
        }
        expected_refs = set(world.artifact_ids.values())
        if set(bible.authoritative_refs) != expected_refs:
            issues.append(
                ReconciliationIssue(
                    "WORLD-REFS",
                    "/authoritative_refs",
                    "must exactly reference every checked world artifact",
                )
            )
        if bible.present_year != world.present_year:
            issues.append(
                ReconciliationIssue(
                    "WORLD-PRESENT-YEAR", "/present_year", f"expected {world.present_year}"
                )
            )
        region_facts = {fact.fact_id: fact.value for fact in world.regions()}
        region_claims = {claim.region_id: claim for claim in bible.regions}
        if set(region_claims) != set(region_facts):
            issues.append(
                ReconciliationIssue(
                    "WORLD-REGION-COVERAGE",
                    "/regions",
                    "all authoritative regions must be addressed",
                )
            )
        for index, claim in enumerate(bible.regions):
            path = f"/regions/{index}"
            fact = region_facts.get(claim.region_id)
            if fact is None:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-REGION-UNKNOWN", path + "/region_id", claim.region_id
                    )
                )
                continue
            checks = (
                ("center", claim.center, fact["center"], "WORLD-COORDINATE"),
                ("biome_id", claim.biome_id, fact["biome_id"], "WORLD-BIOME"),
                ("climate_regime", claim.climate_regime, fact["climate_regime"], "WORLD-CLIMATE"),
                ("resources", tuple(claim.resources), tuple(fact["resources"]), "WORLD-RESOURCE"),
                ("neighbors", tuple(claim.neighbors), tuple(fact["neighbors"]), "WORLD-ADJACENCY"),
            )
            for field, actual, expected, code in checks:
                if actual != expected:
                    issues.append(
                        ReconciliationIssue(code, f"{path}/{field}", f"expected {expected!r}")
                    )
        route_facts = {fact.fact_id: fact.value for fact in world.routes()}
        if {claim.route_id for claim in bible.routes} != set(route_facts):
            issues.append(
                ReconciliationIssue(
                    "WORLD-ROUTE-COVERAGE", "/routes", "all authoritative routes must be addressed"
                )
            )
        for index, route_claim in enumerate(bible.routes):
            fact = route_facts.get(route_claim.route_id)
            if fact is None or (route_claim.start_region, route_claim.end_region) != (
                fact["start_region"],
                fact["end_region"],
            ):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-ROUTE", f"/routes/{index}", "unknown or impossible route"
                    )
                )
        site_facts = {fact.fact_id: fact.value for fact in world.sites()}
        if {claim.site_id for claim in bible.sites} != set(site_facts):
            issues.append(
                ReconciliationIssue(
                    "WORLD-SITE-COVERAGE", "/sites", "all authoritative sites must be addressed"
                )
            )
        for index, claim in enumerate(bible.sites):
            fact = site_facts.get(claim.site_id)
            expected = (
                None
                if fact is None
                else (
                    fact["region_id"],
                    fact["cell"],
                    fact["water_access"],
                    fact["resource_access"],
                )
            )
            actual = (claim.region_id, claim.cell, claim.water_access, claim.resource_access)
            if expected is None or actual != expected or claim.region_id not in region_facts:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-SITE",
                        f"/sites/{index}",
                        "site contradicts its authoritative placement",
                    )
                )
        civilization_facts = {fact.fact_id: fact.value for fact in world.civilizations()}
        claimed_civilizations = {claim.civilization_id for claim in bible.civilizations}
        if claimed_civilizations != set(civilization_facts):
            issues.append(
                ReconciliationIssue(
                    "WORLD-CIV-COVERAGE",
                    "/civilizations",
                    "all authoritative civilizations must be addressed",
                )
            )
        for index, civilization_claim in enumerate(bible.civilizations):
            fact = civilization_facts.get(civilization_claim.civilization_id)
            if fact is None:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-CIV-UNKNOWN",
                        f"/civilizations/{index}",
                        civilization_claim.civilization_id,
                    )
                )
                continue
            if civilization_claim.government != fact["government"]:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-GOVERNMENT",
                        f"/civilizations/{index}/government",
                        f"expected {fact['government']}",
                    )
                )
            if tuple(civilization_claim.territory) != tuple(fact["territory"]):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-TERRITORY",
                        f"/civilizations/{index}/territory",
                        "territory contradicts present state",
                    )
                )
        person_facts = {fact.fact_id: fact.value for fact in world.people()}
        if {claim.person_id for claim in bible.people} != set(person_facts):
            issues.append(
                ReconciliationIssue(
                    "WORLD-PERSON-COVERAGE", "/people", "all consequential people must be addressed"
                )
            )
        for index, claim in enumerate(bible.people):
            fact = person_facts.get(claim.person_id)
            expected = (
                None
                if fact is None
                else (
                    fact["civilization_id"],
                    fact["settlement_id"],
                    fact["created_year"],
                    fact["status"],
                    fact["status_year"],
                )
            )
            actual = (
                claim.civilization_id,
                claim.settlement_id,
                claim.created_year,
                claim.status,
                claim.status_year,
            )
            if expected is None or actual != expected:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-PERSON",
                        f"/people/{index}",
                        "person identity or temporal state contradicts history",
                    )
                )
        event_facts = {fact.fact_id: fact.value for fact in world.events()}
        for index, event_claim in enumerate(bible.history):
            fact = event_facts.get(event_claim.event_id)
            if fact is None:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-EVENT-UNKNOWN", f"/history/{index}", event_claim.event_id
                    )
                )
                continue
            if event_claim.year != fact["year"]:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-CHRONOLOGY", f"/history/{index}/year", f"expected {fact['year']}"
                    )
                )
            if tuple(event_claim.causes) != tuple(fact["causes"]):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-CAUSALITY",
                        f"/history/{index}/causes",
                        "event causes contradict ledger",
                    )
                )
            if tuple(event_claim.participants) != tuple(fact["participants"]):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-PARTICIPANTS",
                        f"/history/{index}/participants",
                        "event participants contradict ledger",
                    )
                )
            for participant in event_claim.participants:
                person = person_facts.get(participant)
                if person is None:
                    continue
                if event_claim.year < int(person["created_year"]) or (
                    person["status"] == "dead"
                    and person["status_year"] is not None
                    and event_claim.year > int(person["status_year"])
                ):
                    issues.append(
                        ReconciliationIssue(
                            "WORLD-PERSON-TEMPORAL",
                            f"/history/{index}/participants",
                            "event uses a person before creation or after death",
                        )
                    )
        valid_containers = (
            set(region_facts) | {fact.fact_id for fact in world.sites()} | set(civilization_facts)
        )
        valid_facts = valid_containers | set(event_facts) | set(person_facts)
        for index, entity in enumerate(bible.local_entities):
            if entity.contained_by not in valid_containers:
                issues.append(
                    ReconciliationIssue(
                        "WORLD-CONTAINER",
                        f"/local_entities/{index}/contained_by",
                        "local entity must name a valid container",
                    )
                )
            if not entity.authoritative_refs or any(
                ref not in valid_facts for ref in entity.authoritative_refs
            ):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-LOCAL-REF",
                        f"/local_entities/{index}/authoritative_refs",
                        "unknown authoritative fact reference",
                    )
                )
        identities = world.identities().value
        laws = {law["law_id"]: law for law in identities["magic_laws"]}
        religions = {religion["religion_id"]: religion for religion in identities["religions"]}
        for index, magic_claim in enumerate(bible.magic_claims):
            if (
                magic_claim.epistemic_status == "objective"
                and magic_claim.authoritative_ref not in laws
            ):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-MAGIC-LAW",
                        f"/magic_claims/{index}",
                        "objective claim lacks an objective law",
                    )
                )
            elif (
                magic_claim.epistemic_status == "objective"
                and magic_claim.statement != laws[magic_claim.authoritative_ref]["effect"]
            ):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-MAGIC-CONTRADICTION",
                        f"/magic_claims/{index}/statement",
                        "objective effect contradicts its law",
                    )
                )
            if (
                magic_claim.epistemic_status == "belief"
                and magic_claim.authoritative_ref not in religions
            ):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-BELIEF", f"/magic_claims/{index}", "belief claim lacks a religion"
                    )
                )
            elif (
                magic_claim.epistemic_status == "belief"
                and magic_claim.statement
                != religions[magic_claim.authoritative_ref]["belief_claim"]
            ):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-BELIEF-CONTRADICTION",
                        f"/magic_claims/{index}/statement",
                        "belief must remain an attributed claim",
                    )
                )
        claim_ids = {
            "regions": {item.region_id for item in bible.regions},
            "routes": {item.route_id for item in bible.routes},
            "sites": {item.site_id for item in bible.sites},
            "civilizations": {item.civilization_id for item in bible.civilizations},
            "people": {item.person_id for item in bible.people},
            "history": {item.event_id for item in bible.history},
            "identities": {item.authoritative_ref for item in bible.magic_claims},
        }
        for category, ids in claim_ids.items():
            if not ids <= projected.get(category, set()):
                issues.append(
                    ReconciliationIssue(
                        "WORLD-PROJECTION-SOURCE",
                        f"/{category}",
                        "Bible claim is absent from the validated projection",
                    )
                )
        # Semantic criticism can add warnings, never erase deterministic errors.
        issues.extend(
            ReconciliationIssue("CRITIC", "/interpretations", issue, "warning")
            for issue in critic_issues
        )
        accepted = not any(issue.severity == "error" for issue in issues)
        return ReconciliationReport(
            accepted,
            world.artifact_ids,
            world.file_hashes,
            self.RULESET_VERSION,
            tuple(issues),
            critic_status,
            hashlib.sha256(canonical_json(projections)).hexdigest(),
        )
