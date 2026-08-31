"""Bounded, reveal-safe access contract for Game Master knowledge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

MAX_NORMALIZED_TEXT_BYTES = 2048


def bounded_normalized_text(value: str) -> str:
    """Return a deterministic valid-UTF-8 prefix for a packaged excerpt."""
    payload = value.encode("utf-8")
    if len(payload) <= MAX_NORMALIZED_TEXT_BYTES:
        return value
    return payload[:MAX_NORMALIZED_TEXT_BYTES].decode("utf-8", errors="ignore").rstrip()


@dataclass(frozen=True)
class KnowledgeExcerpt:
    """Small searchable projection; never an authoritative world record."""

    entry_id: str
    kind: str
    normalized_text: str
    source_ids: tuple[str, ...]
    incoming_refs: tuple[str, ...]
    outgoing_refs: tuple[str, ...]
    reveal_after_nodes: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeReadCounters:
    """Physical work performed for one source request."""

    bytes_read: int = 0
    chunks_opened: int = 0
    records_decoded: int = 0


@dataclass(frozen=True)
class KnowledgeRead:
    excerpts: tuple[KnowledgeExcerpt, ...]
    counters: KnowledgeReadCounters


@runtime_checkable
class KnowledgeSource(Protocol):
    """Read a bounded reveal-safe subset of a packaged knowledge catalog."""

    def read(
        self,
        *,
        entry_ids: frozenset[str] = frozenset(),
        query_tokens: frozenset[str] = frozenset(),
        visited_nodes: frozenset[str] = frozenset(),
        max_records: int,
        max_excerpt_bytes: int,
    ) -> KnowledgeRead:
        """Return only eligible excerpts within both explicit bounds."""
        ...


@dataclass(frozen=True)
class _Locator:
    entry_id: str
    tokens: frozenset[str]
    reveal_after_nodes: frozenset[str]
    relative_path: str
    sha256: str
    size_bytes: int


class DirectoryKnowledgeSource:
    """Read content-addressed excerpt chunks through a small locator catalog."""

    def __init__(self, root: Path, catalog_name: str = "index.json") -> None:
        self._root = root.resolve()
        raw = json.loads((self._root / catalog_name).read_bytes())
        if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
            raise ValueError("KNOWLEDGE_INDEX_FORMAT")
        locators: list[_Locator] = []
        for item in raw["entries"]:
            if not isinstance(item, dict):
                raise ValueError("KNOWLEDGE_INDEX_ENTRY")
            try:
                entry_id = item["entry_id"]
                tokens = item["tokens"]
                reveal = item["reveal_after_nodes"]
                relative_path = item["path"]
                sha256 = item["sha256"]
                size_bytes = item["size_bytes"]
            except KeyError as exc:
                raise ValueError("KNOWLEDGE_INDEX_ENTRY") from exc
            if (
                not isinstance(entry_id, str)
                or not isinstance(tokens, list)
                or not all(isinstance(value, str) for value in tokens)
                or not isinstance(reveal, list)
                or not all(isinstance(value, str) for value in reveal)
                or not isinstance(relative_path, str)
                or not isinstance(sha256, str)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or not isinstance(size_bytes, int)
                or isinstance(size_bytes, bool)
                or size_bytes < 0
            ):
                raise ValueError("KNOWLEDGE_INDEX_ENTRY")
            if (
                relative_path.startswith("/")
                or "\\" in relative_path
                or any(part in {"", ".", ".."} for part in relative_path.split("/"))
                or tokens != sorted(set(tokens))
                or reveal != sorted(set(reveal))
            ):
                raise ValueError("KNOWLEDGE_INDEX_ENTRY")
            locators.append(
                _Locator(
                    entry_id,
                    frozenset(tokens),
                    frozenset(reveal),
                    relative_path,
                    sha256,
                    size_bytes,
                )
            )
        if len({item.entry_id for item in locators}) != len(locators):
            raise ValueError("KNOWLEDGE_INDEX_DUPLICATE_ID")
        self._locators = tuple(sorted(locators, key=lambda item: item.entry_id))

    def read(
        self,
        *,
        entry_ids: frozenset[str] = frozenset(),
        query_tokens: frozenset[str] = frozenset(),
        visited_nodes: frozenset[str] = frozenset(),
        max_records: int,
        max_excerpt_bytes: int,
    ) -> KnowledgeRead:
        if max_records < 0 or max_excerpt_bytes < 0:
            raise ValueError("knowledge bounds must be non-negative")
        if max_records == 0 or max_excerpt_bytes == 0:
            return KnowledgeRead((), KnowledgeReadCounters())
        selected = (
            locator
            for locator in self._locators
            if (not entry_ids or locator.entry_id in entry_ids)
            and (not query_tokens or not locator.tokens.isdisjoint(query_tokens))
            and locator.reveal_after_nodes.issubset(visited_nodes)
        )
        excerpts: list[KnowledgeExcerpt] = []
        bytes_read = 0
        chunks_opened = 0
        decoded = 0
        for locator in selected:
            if len(excerpts) == max_records:
                break
            if bytes_read + locator.size_bytes > max_excerpt_bytes:
                continue
            path = (self._root / locator.relative_path).resolve()
            if self._root not in path.parents:
                raise ValueError("KNOWLEDGE_CHUNK_PATH")
            if path.stat().st_size != locator.size_bytes:
                raise ValueError("KNOWLEDGE_CHUNK_SIZE")
            payload = path.read_bytes()
            chunks_opened += 1
            bytes_read += len(payload)
            if hashlib.sha256(payload).hexdigest() != locator.sha256:
                raise ValueError("KNOWLEDGE_CHUNK_HASH")
            data = json.loads(payload)
            decoded += 1
            excerpt = _decode_excerpt(data)
            if excerpt.entry_id != locator.entry_id:
                raise ValueError("KNOWLEDGE_CHUNK_ID")
            if frozenset(excerpt.reveal_after_nodes) != locator.reveal_after_nodes:
                raise ValueError("KNOWLEDGE_CHUNK_REVEAL")
            excerpts.append(excerpt)
        return KnowledgeRead(
            tuple(excerpts), KnowledgeReadCounters(bytes_read, chunks_opened, decoded)
        )


def _decode_excerpt(data: object) -> KnowledgeExcerpt:
    if not isinstance(data, dict):
        raise ValueError("KNOWLEDGE_CHUNK_FORMAT")

    def strings(name: str) -> tuple[str, ...]:
        value = data.get(name)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("KNOWLEDGE_CHUNK_FORMAT")
        return tuple(value)

    entry_id = data.get("entry_id")
    kind = data.get("kind")
    normalized_text = data.get("normalized_text")
    if not all(isinstance(value, str) for value in (entry_id, kind, normalized_text)):
        raise ValueError("KNOWLEDGE_CHUNK_FORMAT")
    assert isinstance(entry_id, str)
    assert isinstance(kind, str)
    assert isinstance(normalized_text, str)
    return KnowledgeExcerpt(
        entry_id,
        kind,
        normalized_text,
        strings("source_ids"),
        strings("incoming_refs"),
        strings("outgoing_refs"),
        strings("reveal_after_nodes"),
    )
