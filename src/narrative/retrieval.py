"""Deterministic cross-platform GM knowledge retrieval contract."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from .models import KnowledgeEntry
from .scoring import SCORING

DEFAULT_CONTEXT_BUDGET_BYTES = 4096
DEFAULT_MAX_RESULTS = 8


@dataclass(frozen=True)
class KnowledgeHit:
    entry: KnowledgeEntry
    score: int
    prompt_line: str


def normalize_query(value: str) -> str:
    """NFKC, lowercase, collapse every non-alphanumeric run to one space."""
    normalized = unicodedata.normalize("NFKC", value).lower()
    separated = "".join(character if character.isalnum() else " " for character in normalized)
    return " ".join(separated.split())


def query_tokens(value: str) -> tuple[str, ...]:
    return tuple(sorted(set(normalize_query(value).split())))


def filter_revealed_entries(
    entries: Iterable[KnowledgeEntry], visited_nodes: frozenset[str]
) -> tuple[KnowledgeEntry, ...]:
    """Remove unrevealed facts before any searchable text is constructed.

    This is the spoiler-security boundary.  Callers may inspect the returned
    entries in tests/debugging, but must never log rejected entries.
    """
    return tuple(
        entry
        for entry in entries
        if not entry.reveal_after_nodes
        or frozenset(entry.reveal_after_nodes).issubset(visited_nodes)
    )


def retrieve_knowledge(
    entries: Iterable[KnowledgeEntry],
    query: str,
    visited_nodes: frozenset[str],
    *,
    context_budget_bytes: int = DEFAULT_CONTEXT_BUDGET_BYTES,
    max_results: int = DEFAULT_MAX_RESULTS,
    current_node_id: str | None = None,
    visited_refs: frozenset[str] = frozenset(),
) -> tuple[KnowledgeHit, ...]:
    if context_budget_bytes < 0 or max_results < 0:
        raise ValueError("retrieval budgets must be non-negative")
    normalized = normalize_query(query)
    tokens = query_tokens(query)
    if not tokens or not normalized or context_budget_bytes == 0 or max_results == 0:
        return ()

    eligible = filter_revealed_entries(entries, visited_nodes)
    if not eligible:
        return ()

    token_set = frozenset(tokens)

    # Compute recency ranks: index in visited_nodes (order matters)
    visited_list = sorted(visited_nodes) if visited_nodes else []
    recency: dict[str, int] = {}
    for i, nid in enumerate(reversed(visited_list)):
        recency[nid] = i

    ranked: list[tuple[tuple[int, str], KnowledgeEntry]] = []
    for entry in eligible:
        # Determine recency rank from reveal_after_nodes
        recency_rank: int | None = None
        if entry.reveal_after_nodes:
            ranks = [recency[n] for n in entry.reveal_after_nodes if n in recency]
            if ranks:
                recency_rank = min(ranks)  # most recent wins

        score = SCORING.score(
            entry,
            token_set,
            normalized,
            current_node_id=current_node_id,
            visited_refs=visited_refs,
            recency_rank=recency_rank,
        )
        if score > 0:
            ranked.append((SCORING.rank_key(entry, score), entry))

    ranked.sort(key=lambda item: item[0])

    remaining = context_budget_bytes
    selected: list[KnowledgeHit] = []
    for (neg_score, _), entry in ranked:
        line = f"[{entry.entry_id}] ({entry.kind}) {entry.normalized_text}"
        cost = len(line.encode("utf-8")) + (1 if selected else 0)
        if cost > remaining:
            continue
        selected.append(KnowledgeHit(entry, -neg_score, line))
        remaining -= cost
        if len(selected) == max_results:
            break
    return tuple(selected)


def format_knowledge_prompt(hits: Iterable[KnowledgeHit]) -> str:
    return "\n".join(hit.prompt_line for hit in hits)
