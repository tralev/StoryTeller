"""Deterministic source-addressed, token-budgeted prompt projections."""
from __future__ import annotations

from dataclasses import dataclass

from ..worldgen.artifacts import canonical_json
from .views import WorldFact, WorldView


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
    records: tuple[ProjectionRecord, ...]
    estimated_tokens: int


@dataclass(frozen=True)
class ProjectionSet:
    chunks: tuple[ProjectionChunk, ...]
    source_coverage: dict[str, tuple[int, int]]


def _record(fact: WorldFact, fields: tuple[str, ...]) -> ProjectionRecord:
    compact = {field: fact.value.get(field) for field in fields if field in fact.value}
    text = canonical_json(compact).decode("utf-8")
    return ProjectionRecord(fact.fact_id, fact.kind, text, fact.source_ids,
                            max(1, (len(text) + 3) // 4))


def build_projections(view: WorldView, *, token_budget: int = 8_000,
                      history_limit: int = 200) -> ProjectionSet:
    if token_budget < 64 or history_limit < 0:
        raise ValueError("projection budget must be at least 64 tokens")
    groups: list[tuple[str, tuple[WorldFact, ...], tuple[str, ...]]] = [
        ("regions", view.regions(), ("region_id", "center", "neighbors", "biome_id", "climate_regime", "resources")),
        ("routes", view.routes(), ("route_id", "start_region", "end_region", "distance_m", "seasonal_risk_ppm")),
        ("sites", view.sites(), ("site_id", "region_id", "cell", "water_access", "resource_access")),
        ("civilizations", view.civilizations(), ("civilization_id", "name", "culture", "government", "territory", "population")),
    ]
    material_events = view.events(("war", "peace", "conquest", "collapse", "recovery", "technology",
                                   "reform", "schism", "succession", "construction", "exploration"))
    selected_history = material_events[-history_limit:] if history_limit else ()
    groups.append(("history", selected_history,
                   ("event_id", "year", "month", "kind", "causes", "participants", "locations", "summary")))
    chunks: list[ProjectionChunk] = []
    current: list[ProjectionRecord] = []
    current_tokens = 0
    coverage: dict[str, tuple[int, int]] = {}
    for category, facts, fields in groups:
        included = 0
        for fact in facts:
            record = _record(fact, fields)
            if record.estimated_tokens > token_budget:
                raise ValueError(f"projection record exceeds token budget: {record.record_id}")
            if current and current_tokens + record.estimated_tokens > token_budget:
                chunks.append(ProjectionChunk(f"chunk_{len(chunks) + 1:04d}", tuple(current), current_tokens))
                current, current_tokens = [], 0
            current.append(record); current_tokens += record.estimated_tokens; included += 1
        coverage[category] = (included, len(facts))
    if current:
        chunks.append(ProjectionChunk(f"chunk_{len(chunks) + 1:04d}", tuple(current), current_tokens))
    coverage["history"] = (len(selected_history), len(material_events))
    return ProjectionSet(tuple(chunks), coverage)
