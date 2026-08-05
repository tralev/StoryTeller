"""Deterministic cross-platform GM knowledge retrieval contract."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .models import KnowledgeEntry

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
) -> tuple[KnowledgeHit, ...]:
    if context_budget_bytes < 0 or max_results < 0:
        raise ValueError("retrieval budgets must be non-negative")
    normalized = normalize_query(query)
    tokens = query_tokens(query)
    if not tokens or not normalized or context_budget_bytes == 0 or max_results == 0:
        return ()

    ranked: list[tuple[int, str, KnowledgeEntry]] = []
    for entry in filter_revealed_entries(entries, visited_nodes):
        searchable = normalize_query(" ".join((entry.kind, entry.normalized_text, *entry.source_ids)))
        searchable_tokens = frozenset(searchable.split())
        score = 100 * sum(token in searchable_tokens for token in tokens)
        if normalized in searchable:
            score += 500
        if score:
            ranked.append((-score, entry.entry_id, entry))

    remaining = context_budget_bytes
    selected: list[KnowledgeHit] = []
    for negative_score, _, entry in sorted(ranked):
        line = f"[{entry.entry_id}] ({entry.kind}) {entry.normalized_text}"
        cost = len(line.encode("utf-8")) + (1 if selected else 0)
        if cost > remaining:
            continue
        selected.append(KnowledgeHit(entry, -negative_score, line))
        remaining -= cost
        if len(selected) == max_results:
            break
    return tuple(selected)


def format_knowledge_prompt(hits: Iterable[KnowledgeHit]) -> str:
    return "\n".join(hit.prompt_line for hit in hits)
