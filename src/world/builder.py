"""Checkpointed candidate/reconcile loop for authoritative Bible enrichment."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Protocol
from jinja2 import Template

from ..storage.fs import atomic_write_bytes
from ..worldgen.artifacts import canonical_json
from ..worldgen.numeric import identity, stable_id
from .models import (BibleV2, CivilizationClaim, EventClaim, LocalEntity, MagicClaim,
                     RegionClaim, RouteClaim)
from .projections import ProjectionSet, build_projections
from .views import WorldView
from ..validators.world_reconciler import ReconciliationReport, WorldReconciler


class SemanticCritic(Protocol):
    def critique(self, bible: BibleV2, projections: ProjectionSet) -> tuple[str, ...]: ...


CandidateFactory = Callable[[WorldView, str, str, int], BibleV2]


def deterministic_candidate(world: WorldView, title: str, feedback: str, attempt: int) -> BibleV2:
    del feedback, attempt
    regions = tuple(RegionClaim(fact.fact_id, int(fact.value["center"]), int(fact.value["biome_id"]),
                                int(fact.value["climate_regime"]), tuple(fact.value["resources"]),
                                tuple(fact.value["neighbors"])) for fact in world.regions())
    routes = tuple(RouteClaim(fact.fact_id, str(fact.value["start_region"]), str(fact.value["end_region"]))
                   for fact in world.routes())
    civilizations = tuple(CivilizationClaim(fact.fact_id, str(fact.value["name"]),
                                             str(fact.value["government"]), tuple(fact.value["territory"]))
                          for fact in world.civilizations())
    material = world.events(("war", "peace", "conquest", "collapse", "recovery", "technology",
                             "reform", "schism", "succession", "construction", "exploration"))
    history = tuple(EventClaim(fact.fact_id, int(fact.value["year"]), tuple(fact.value["causes"]))
                    for fact in material)
    local_entities = tuple(LocalEntity(stable_id(
                                       "local", world.present_year,
                                       identity("site_id", fact.fact_id),
                                       identity("detail_kind", ("building", "street", "cave", "ruin", "item", "minor_character")[index % 6]),
                                       ),
                                       ("building", "street", "cave", "ruin", "item", "minor_character")[index % 6],
                                       f"Recorded Local Detail {index + 1}", fact.value["region_id"],
                                       (fact.value["region_id"], fact.fact_id))
                           for index, fact in enumerate(world.sites()))
    identities = world.identities().value
    magic_claims = tuple(
        [MagicClaim(str(law["law_id"]), str(law["effect"]), "objective", str(law["law_id"]))
         for law in identities["magic_laws"]]
        + [MagicClaim(str(religion["religion_id"]), str(religion["belief_claim"]), "belief",
                      str(religion["religion_id"])) for religion in identities["religions"]]
    )
    interpretations = ("A mature dark-fantasy interpretation of documented geography and history.",
                       "Beliefs remain attributed claims; objective magic remains constrained by recorded laws.")
    return BibleV2("2-pre1", title, world.present_year,
                   tuple(sorted(world.artifact_ids.values())), regions, routes, civilizations, history,
                   local_entities, magic_claims, interpretations)


class WorldBuilderV2:
    def __init__(self, *, reconciler: WorldReconciler | None = None,
                 critic: SemanticCritic | None = None, max_attempts: int = 3,
                 candidate_factory: CandidateFactory = deterministic_candidate) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.reconciler = reconciler or WorldReconciler()
        self.critic = critic
        self.max_attempts = max_attempts
        self.candidate_factory = candidate_factory

    @staticmethod
    def render_prompt(title: str, projections: ProjectionSet, retry_feedback: str = "") -> str:
        template_path = Path(__file__).resolve().parents[1] / "prompts" / "world_builder_v2_authoritative.j2"
        template = Template(template_path.read_text())
        chunks = tuple(tuple({"record_id": record.record_id, "fact": record.fact,
                              "source_ids": record.source_ids} for record in chunk.records)
                       for chunk in projections.chunks)
        return template.render(title=title, projection_chunks=chunks, retry_feedback=retry_feedback)

    def build(self, world_path: str | Path, title: str, output: str | Path) -> tuple[BibleV2, ReconciliationReport]:
        world = WorldView(world_path)
        before = world.file_hashes
        projections = build_projections(world)
        output_path = Path(output)
        feedback = ""
        last_report: ReconciliationReport | None = None
        for attempt in range(1, self.max_attempts + 1):
            prompt = self.render_prompt(title, projections, feedback)
            atomic_write_bytes(output_path / "checkpoints" / f"world_builder_prompt_{attempt:02d}.txt",
                               prompt.encode("utf-8"))
            candidate = self.candidate_factory(world, title, feedback, attempt)
            atomic_write_bytes(output_path / "checkpoints" / f"bible_candidate_{attempt:02d}.json",
                               canonical_json(candidate))
            critic_issues: tuple[str, ...] = ()
            critic_status = "not_requested"
            if self.critic is not None:
                try:
                    critic_issues = self.critic.critique(candidate, projections)
                    critic_status = "completed"
                except Exception:
                    critic_status = "failed_optional"
            report = self.reconciler.reconcile(world, candidate, critic_issues=critic_issues,
                                               critic_status=critic_status)
            world.assert_unchanged(before)
            last_report = report
            if report.accepted:
                atomic_write_bytes(output_path / "bible.json", canonical_json(candidate))
                atomic_write_bytes(output_path / "reconciliation.json", canonical_json(report))
                projection_manifest = {
                    "chunks": len(projections.chunks), "source_coverage": projections.source_coverage,
                    "sha256": hashlib.sha256(canonical_json(projections)).hexdigest(),
                }
                atomic_write_bytes(output_path / "projection_manifest.json", canonical_json(projection_manifest))
                return candidate, report
            feedback = report.retry_feedback()
        assert last_report is not None
        atomic_write_bytes(output_path / "reconciliation.json", canonical_json(last_report))
        raise ValueError("Bible reconciliation failed after bounded retries:\n" + last_report.retry_feedback())
