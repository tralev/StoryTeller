"""P8.WG3 — Procedural spoiler proof via unique sentinel strings.

Sentinel strings are embedded in unrevealed facts, history changes,
local maps, beliefs, opportunities, IDs, and source IDs. Before reveal,
they must not appear in candidates, ranking diagnostics, prompt text,
errors, logs, or saved history. After reveal, verified presence proves
the sentinel tracking is correct.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from .models import KnowledgeEntry

# Stable sentinel prefix so tests can recognize them without relying on
# the unpredictable suffix (which is why they cannot be guessed).
SENTINEL_PREFIX = "\u200bspoiler-proof-"


@dataclass(frozen=True)
class Sentinel:
    """A unique unrevealed-content marker that cannot be guessed.

    The prefix is constant and documented; the suffix is 16 hex bytes
    derived from ``secrets.token_hex(16)``. In production builds the
    sentinel value is frozen in the generated world and shared across
    Python, Android, and iOS fixtures.
    """

    sentinel_id: str
    suffix: str
    entry_ids: tuple[str, ...]

    @property
    def marker(self) -> str:
        return f"{SENTINEL_PREFIX}{self.suffix}"

    @classmethod
    def generate(cls, sentinel_id: str, entry_ids: tuple[str, ...]) -> Sentinel:
        return cls(sentinel_id, secrets.token_hex(16), entry_ids)

    @classmethod
    def deterministic(cls, sentinel_id: str, seed: int, entry_ids: tuple[str, ...]) -> Sentinel:
        """Deterministic sentinel for test fixtures (not production)."""
        raw = hashlib.sha256(f"{sentinel_id}:{seed}".encode()).hexdigest()[:32]
        return cls(sentinel_id, raw, entry_ids)


@dataclass(frozen=True)
class SpoilerReport:
    """Result of scanning a boundary surface for sentinel leaks."""

    boundary_name: str
    sentinel_ids_found: tuple[str, ...]
    marker_snippets: tuple[str, ...]

    @property
    def leaked(self) -> bool:
        return len(self.sentinel_ids_found) > 0

    @property
    def clean(self) -> bool:
        return not self.leaked


class SpoilerGate:
    """Inject sentinels into knowledge entries and verify boundary surfaces."""

    def __init__(self, sentinels: tuple[Sentinel, ...]) -> None:
        self._sentinels = sentinels
        self._by_entry: dict[str, Sentinel] = {}
        for s in sentinels:
            for eid in s.entry_ids:
                self._by_entry[eid] = s

    @property
    def sentinels(self) -> tuple[Sentinel, ...]:
        return self._sentinels

    def inject(self, entries: tuple[KnowledgeEntry, ...]) -> tuple[KnowledgeEntry, ...]:
        """Return entries with sentinel markers embedded in unrevealed text."""
        result: list[KnowledgeEntry] = []
        for entry in entries:
            sentinel = self._by_entry.get(entry.entry_id)
            if sentinel is None or not entry.reveal_after_nodes:
                result.append(entry)
                continue
            # Inject marker into normalized_text and source_ids
            marked_text = f"{entry.normalized_text} {sentinel.marker}"
            marked_sources = (*entry.source_ids, sentinel.marker)
            result.append(KnowledgeEntry(
                entry.entry_id, entry.kind, marked_text, marked_sources,
                entry.incoming_refs, entry.outgoing_refs, entry.reveal_after_nodes,
            ))
        return tuple(result)

    def scan(self, boundary_name: str, text: str) -> SpoilerReport:
        """Scan a text boundary for any sentinel markers."""
        found_ids: list[str] = []
        snippets: list[str] = []
        for sentinel in self._sentinels:
            idx = text.find(sentinel.marker)
            if idx >= 0:
                found_ids.append(sentinel.sentinel_id)
                start = max(0, idx - 20)
                end = min(len(text), idx + len(sentinel.marker) + 20)
                snippets.append(text[start:end])
        return SpoilerReport(boundary_name, tuple(found_ids), tuple(snippets))

    def scan_candidates(self, entries: tuple[KnowledgeEntry, ...]) -> SpoilerReport:
        """Scan candidate entries (before reveal filtering)."""
        text = " ".join(
            f"{e.entry_id} {e.kind} {e.normalized_text} {' '.join(e.source_ids)}"
            for e in entries
        )
        return self.scan("candidates", text)

    def scan_prompt(self, prompt: str) -> SpoilerReport:
        """Scan the GM prompt text."""
        return self.scan("prompt", prompt)

    def scan_hits(self, hits_text: str) -> SpoilerReport:
        """Scan formatted knowledge hits text."""
        return self.scan("hits", hits_text)

    def scan_error(self, exception_or_message: BaseException | str) -> SpoilerReport:
        """Scan an error/exception for sentinel leaks.

        P8.WG3: Error messages must never contain unrevealed sentinel markers.
        """
        if isinstance(exception_or_message, BaseException):
            text = " ".join(str(a) for a in exception_or_message.args)
        else:
            text = exception_or_message
        return self.scan("error", text)

    def scan_log(self, log_line: str) -> SpoilerReport:
        """Scan a log line for sentinel leaks.

        P8.WG3: Log output must never contain unrevealed sentinel markers.
        """
        return self.scan("log", log_line)

    def scan_saved_history(self, serialized: str) -> SpoilerReport:
        """Scan saved/persisted history for sentinel leaks.

        P8.WG3: Saved conversation history must never contain
        unrevealed sentinel markers.
        """
        return self.scan("saved_history", serialized)

    def get_sentinel(self, entry_id: str) -> Sentinel | None:
        return self._by_entry.get(entry_id)

    @property
    def sentinel_count(self) -> int:
        return len(self._sentinels)


def build_spoiler_gate(
    entries: tuple[KnowledgeEntry, ...],
    domains: tuple[str, ...] = ("global", "history", "local_maps", "beliefs", "opportunities"),
    seed: int = 42,
) -> SpoilerGate:
    """Build a SpoilerGate covering every unrevealed entry in named domains.

    In production the seed is derived from the world seed; for tests use a
    fixed seed.
    """
    sentinels: list[Sentinel] = []
    # Group unrevealed entries by domain
    domain_entries: dict[str, list[str]] = {d: [] for d in domains}
    for entry in entries:
        if not entry.reveal_after_nodes:
            continue
        # Classify into domain based on kind
        domain = _classify_domain(entry, domains)
        domain_entries[domain].append(entry.entry_id)

    for domain, eids in domain_entries.items():
        if eids:
            sid = f"sentinel_{domain}"
            sentinels.append(Sentinel.deterministic(sid, seed, tuple(sorted(eids))))

    return SpoilerGate(tuple(sentinels))


def _classify_domain(entry: KnowledgeEntry, domains: tuple[str, ...]) -> str:
    kind = entry.kind
    if kind in ("event",):
        return "history" if "history" in domains else domains[0]
    if kind in ("local_map", "bible_local"):
        return "local_maps" if "local_maps" in domains else domains[0]
    if kind in ("opportunity",):
        return "opportunities" if "opportunities" in domains else domains[0]
    if kind in ("belief",):
        return "beliefs" if "beliefs" in domains else domains[0]
    return "global"


__all__ = [
    "Sentinel", "SpoilerGate", "SpoilerReport", "SENTINEL_PREFIX",
    "build_spoiler_gate",
]
