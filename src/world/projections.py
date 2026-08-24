"""Bounded, typed, source-addressed World Bible prompt projections."""

from __future__ import annotations

from dataclasses import dataclass

from ..worldgen.artifacts import canonical_json
from .views import AuthoritativeArtifactIdentity, WorldFact, WorldView

PROJECTION_FORMAT = "storyteller.bible-projection.v1"
PROJECTION_CATEGORIES = (
    "regions",
    "routes",
    "sites",
    "civilizations",
    "people",
    "history",
    "identities",
    "megabeasts",
    "legendary_artifacts",
)
MAX_PROJECTION_TOKENS = 8_000
MAX_RECORDS_PER_CHUNK = 128


@dataclass(frozen=True)
class ProjectionRecord:
    record_id: str
    category: str
    fact: str
    source_ids: tuple[str, ...]
    estimated_tokens: int


@dataclass(frozen=True)
class ProjectionChunk:
    chunk_id: str
    category: str
    records: tuple[ProjectionRecord, ...]
    estimated_tokens: int


@dataclass(frozen=True)
class ProjectionCoverage:
    category: str
    included: int
    available: int
    selection_policy: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionSet:
    format: str
    authoritative_world: tuple[AuthoritativeArtifactIdentity, ...]
    chunks: tuple[ProjectionChunk, ...]
    source_coverage: tuple[ProjectionCoverage, ...]
    token_budget: int
    history_limit: int


def _record(category: str, fact: WorldFact, fields: tuple[str, ...]) -> ProjectionRecord:
    compact = {field: fact.value[field] for field in fields if field in fact.value}
    text = canonical_json(compact).decode("utf-8")
    return ProjectionRecord(
        fact.fact_id,
        category,
        text,
        tuple(sorted(set(fact.source_ids))),
        max(1, (len(text) + 3) // 4),
    )


def _identity_facts(view: WorldView) -> tuple[WorldFact, ...]:
    identities = view.identities()
    result = []
    for law in identities.value["magic_laws"]:
        result.append(
            WorldFact(
                str(law["law_id"]),
                "identity",
                dict(law),
                identities.source_ids,
            )
        )
    for religion in identities.value["religions"]:
        result.append(
            WorldFact(
                str(religion["religion_id"]),
                "identity",
                dict(religion),
                identities.source_ids,
            )
        )
    return tuple(sorted(result, key=lambda item: item.fact_id))


def build_projections(
    view: WorldView,
    *,
    token_budget: int = MAX_PROJECTION_TOKENS,
    history_limit: int = 200,
) -> ProjectionSet:
    """Build independently bounded category chunks without copying the full world."""
    if not 64 <= token_budget <= MAX_PROJECTION_TOKENS or history_limit < 0:
        raise ValueError("projection limits are outside the frozen bounds")
    material_events = view.events(
        (
            "war",
            "peace",
            "conquest",
            "collapse",
            "recovery",
            "technology",
            "reform",
            "schism",
            "succession",
            "construction",
            "exploration",
        )
    )
    selected_history = material_events[-history_limit:] if history_limit else ()
    groups = (
        (
            "regions",
            view.regions(),
            ("region_id", "center", "neighbors", "biome_id", "climate_regime", "resources"),
            "all",
        ),
        (
            "routes",
            view.routes(),
            ("route_id", "start_region", "end_region", "distance_m", "seasonal_risk_ppm"),
            "all",
        ),
        (
            "sites",
            view.sites(),
            ("site_id", "region_id", "cell", "water_access", "resource_access"),
            "all",
        ),
        (
            "civilizations",
            view.civilizations(),
            ("civilization_id", "name", "culture", "government", "territory", "population"),
            "all",
        ),
        (
            "people",
            view.people(),
            (
                "person_id",
                "civilization_id",
                "settlement_id",
                "created_year",
                "status",
                "status_year",
            ),
            "all",
        ),
        (
            "history",
            selected_history,
            ("event_id", "year", "month", "kind", "causes", "participants", "locations", "summary"),
            "latest_material_events",
        ),
        (
            "identities",
            _identity_facts(view),
            ("law_id", "effect", "religion_id", "belief_claim", "tradition"),
            "all",
        ),
        (
            "megabeasts",
            view.megabeasts(),
            ("megabeast_id", "origin_species_id", "region_id", "condition",
             "lair_site_id", "territory_region_ids"),
            "all",
        ),
        (
            "legendary_artifacts",
            view.legendary_artifacts(),
            ("artifact_id", "name", "creator_id", "culture_id", "site_id",
             "current_site_id", "owner_id", "status", "attributed_meaning"),
            "all",
        ),
    )
    chunks: list[ProjectionChunk] = []
    coverage: list[ProjectionCoverage] = []
    for category, facts, fields, policy in groups:
        records = tuple(
            sorted(
                (_record(category, fact, fields) for fact in facts),
                key=lambda item: item.record_id,
            )
        )
        current: list[ProjectionRecord] = []
        current_tokens = 0
        category_chunk = 0
        for record in records:
            if record.estimated_tokens > token_budget:
                raise ValueError(f"projection record exceeds token budget: {record.record_id}")
            if current and (
                current_tokens + record.estimated_tokens > token_budget
                or len(current) >= MAX_RECORDS_PER_CHUNK
            ):
                category_chunk += 1
                chunks.append(
                    ProjectionChunk(
                        f"{category}_{category_chunk:04d}",
                        category,
                        tuple(current),
                        current_tokens,
                    )
                )
                current, current_tokens = [], 0
            current.append(record)
            current_tokens += record.estimated_tokens
        if current:
            category_chunk += 1
            chunks.append(
                ProjectionChunk(
                    f"{category}_{category_chunk:04d}",
                    category,
                    tuple(current),
                    current_tokens,
                )
            )
        available = len(material_events) if category == "history" else len(facts)
        source_ids = tuple(sorted({source for record in records for source in record.source_ids}))
        coverage.append(
            ProjectionCoverage(
                category,
                len(records),
                available,
                policy,
                source_ids,
            )
        )
    authoritative_world = view.authoritative_inventory()
    result = ProjectionSet(
        PROJECTION_FORMAT,
        authoritative_world,
        tuple(chunks),
        tuple(coverage),
        token_budget,
        history_limit,
    )
    validate_projections(result, authoritative_world)
    return result


def validate_projections(
    projections: ProjectionSet,
    expected_world: tuple[AuthoritativeArtifactIdentity, ...],
) -> None:
    """Reject incomplete, unbounded, reordered, duplicated, or invented projection data."""
    if (
        projections.format != PROJECTION_FORMAT
        or not 64 <= projections.token_budget <= MAX_PROJECTION_TOKENS
        or projections.history_limit < 0
    ):
        raise ValueError("WG-BIBLE-PROJECTION-CONTRACT: invalid projection envelope")
    if (
        not projections.authoritative_world
        or projections.authoritative_world != expected_world
        or projections.authoritative_world != tuple(sorted(projections.authoritative_world))
        or len({item.kind for item in projections.authoritative_world})
        != len(projections.authoritative_world)
    ):
        raise ValueError("WG-BIBLE-PROJECTION-WORLD: incomplete or altered world identity")
    authoritative_ids = {item.artifact_id for item in projections.authoritative_world}
    if tuple(item.category for item in projections.source_coverage) != PROJECTION_CATEGORIES:
        raise ValueError("WG-BIBLE-PROJECTION-COVERAGE: missing or reordered category")
    chunk_ids = tuple(chunk.chunk_id for chunk in projections.chunks)
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("WG-BIBLE-PROJECTION-CHUNK: duplicate chunk identity")
    records_by_category = {category: [] for category in PROJECTION_CATEGORIES}
    for chunk in projections.chunks:
        if (
            chunk.category not in records_by_category
            or not chunk.records
            or len(chunk.records) > MAX_RECORDS_PER_CHUNK
            or chunk.estimated_tokens != sum(item.estimated_tokens for item in chunk.records)
            or chunk.estimated_tokens > projections.token_budget
            or any(item.category != chunk.category for item in chunk.records)
        ):
            raise ValueError("WG-BIBLE-PROJECTION-CHUNK: invalid bounded category chunk")
        records_by_category[chunk.category].extend(chunk.records)
    seen: set[tuple[str, str]] = set()
    for coverage in projections.source_coverage:
        records = records_by_category[coverage.category]
        keys = tuple((item.category, item.record_id) for item in records)
        if (
            keys != tuple(sorted(keys))
            or any(key in seen for key in keys)
            or coverage.included != len(records)
            or not 0 <= coverage.included <= coverage.available
            or coverage.selection_policy not in {"all", "latest_material_events"}
            or (coverage.selection_policy == "all" and coverage.included != coverage.available)
        ):
            raise ValueError("WG-BIBLE-PROJECTION-COVERAGE: invalid selection or ordering")
        seen.update(keys)
        actual_sources = tuple(sorted({source for item in records for source in item.source_ids}))
        if (
            coverage.source_ids != actual_sources
            or any(not item.source_ids for item in records)
            or not set(actual_sources) <= authoritative_ids
        ):
            raise ValueError("WG-BIBLE-PROJECTION-SOURCE: unknown or incomplete source coverage")
