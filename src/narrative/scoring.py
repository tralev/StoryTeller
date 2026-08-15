"""P8.WG2 — Procedural-aware integer scoring for GM knowledge retrieval.

Freeze every scoring weight, tie-break rule, and entity-kind weight here.
The same arithmetic is required on Python, Android (Kotlin), and iOS (Swift).
No embeddings, no platform-dependent tokenizers, no float arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import KnowledgeEntry


@dataclass(frozen=True)
class ScoringWeights:
    """Integer scoring features frozen by P8.WG2."""

    # Base per-token overlap match (multiplied by matching token count)
    token_match: int = 100

    # Bonus when the full normalized query appears verbatim in searchable text
    exact_phrase: int = 500

    # Entry relates directly to the player's current graph node
    current_node: int = 300

    # Entry's source IDs or location references intersect with visited node refs
    visited: int = 200

    # Entity is physically contained within (or contains) a visited location
    containment: int = 250

    # Direct source-ID match with a query token (exact source lookup)
    exact_source: int = 400

    # Recency boost per recency rank (0 = most recent visited, n-1 = oldest)
    # Applied only when an entry's reveal_after_nodes intersects visited_nodes
    recency_base: int = 50
    recency_decay: int = 10


@dataclass(frozen=True)
class KindWeights:
    """Per-entity-kind base score applied to every matching entry."""

    creature: int = 200
    person: int = 180
    event: int = 150
    civilization: int = 140
    settlement: int = 130
    site: int = 120
    location: int = 120
    region: int = 110
    route: int = 100
    artifact: int = 100
    opportunity: int = 160
    local_map: int = 90
    graph_node: int = 80
    story_scene: int = 70
    bible_local: int = 60
    ecology: int = 50
    registries: int = 40
    identities: int = 40
    cohort: int = 40
    # Fallback for unknown kinds
    default_kind: int = 50

    def for_kind(self, kind: str) -> int:
        return _KIND_MAP.get(kind, self.default_kind)


_KIND_MAP: dict[str, int] = {k: getattr(KindWeights(), k) for k in dir(KindWeights()) if not k.startswith("_") and k != "default_kind" and k != "for_kind"}


@dataclass(frozen=True)
class ScoringController:
    """Compute deterministic integer scores for KnowledgeEntry candidates.

    Scores are platform-independent integer arithmetic — no floats, no
    embeddings, no tokenizers beyond fixed Unicode NFKC normalization.
    Tie-break: descending score → ascending entry_id (stable by P8.WG2 contract).
    """

    weights: ScoringWeights = ScoringWeights()
    kind_weights: KindWeights = KindWeights()

    def score(
        self,
        entry: KnowledgeEntry,
        query_tokens: frozenset[str],
        normalized_query: str,
        *,
        current_node_id: str | None = None,
        visited_refs: frozenset[str] = frozenset(),
        recency_rank: int | None = None,
    ) -> int:
        """Return a non-negative integer score. Higher = more relevant."""
        total = self.kind_weights.for_kind(entry.kind)

        # Build searchable text
        searchable = " ".join(
            (entry.kind, entry.normalized_text, *entry.source_ids)
        ).casefold()
        searchable_tokens = frozenset(searchable.split())

        # Token overlap
        matching = sum(1 for t in query_tokens if t in searchable_tokens)
        if matching == 0:
            return 0
        total += self.weights.token_match * matching

        # Exact phrase
        if normalized_query in searchable:
            total += self.weights.exact_phrase

        # Exact source match
        query_source_matches = any(
            q in entry.source_ids for q in query_tokens
        )
        if query_source_matches:
            total += self.weights.exact_source

        # Current node boost
        if current_node_id is not None:
            node_set = frozenset((current_node_id,))
            if frozenset(entry.reveal_after_nodes) & node_set:
                total += self.weights.current_node
            if frozenset(entry.outgoing_refs) & node_set:
                total += self.weights.current_node // 2

        # Visited boost
        if visited_refs:
            if frozenset(entry.source_ids) & visited_refs:
                total += self.weights.visited
            if frozenset(entry.outgoing_refs) & visited_refs:
                total += self.weights.visited // 2

        # Containment boost: entry's incoming/outgoing refs intersect visited
        if visited_refs:
            all_refs = frozenset(entry.outgoing_refs) | frozenset(entry.incoming_refs)
            if all_refs & visited_refs:
                total += self.weights.containment

        # Recency
        if recency_rank is not None and recency_rank >= 0:
            total += max(0, self.weights.recency_base - recency_rank * self.weights.recency_decay)

        return total

    def rank_key(self, entry: KnowledgeEntry, score: int) -> tuple[int, str]:
        """Sort key: descending score then ascending entry_id for stable tie-break."""
        return (-score, entry.entry_id)


SCORING = ScoringController()
