"""Contract tests for the bounded GM knowledge-source port."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from src.narrative.knowledge_source import (
    DirectoryKnowledgeSource,
    KnowledgeExcerpt,
    KnowledgeRead,
    KnowledgeReadCounters,
    KnowledgeSource,
)
from src.narrative.retrieval import retrieve_from_source


class EmptySource:
    def read(
        self,
        *,
        entry_ids: frozenset[str] = frozenset(),
        query_tokens: frozenset[str] = frozenset(),
        visited_nodes: frozenset[str] = frozenset(),
        max_records: int,
        max_excerpt_bytes: int,
    ) -> KnowledgeRead:
        del entry_ids, query_tokens, visited_nodes, max_records, max_excerpt_bytes
        return KnowledgeRead((), KnowledgeReadCounters())


def test_knowledge_source_is_a_runtime_checked_bounded_port() -> None:
    assert isinstance(EmptySource(), KnowledgeSource)


def test_knowledge_read_keeps_excerpts_and_physical_counters_typed() -> None:
    excerpt = KnowledgeExcerpt("id", "event", "small text", ("source",), (), (), ())
    read = KnowledgeRead((excerpt,), KnowledgeReadCounters(10, 1, 1))

    assert read.excerpts == (excerpt,)
    assert read.counters == KnowledgeReadCounters(10, 1, 1)


def _source(tmp_path: Path) -> tuple[DirectoryKnowledgeSource, int]:
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    records = (
        {
            "entry_id": "known",
            "kind": "event",
            "normalized_text": "known eastern gate",
            "source_ids": ["source"],
            "incoming_refs": [],
            "outgoing_refs": [],
            "reveal_after_nodes": [],
        },
        {
            "entry_id": "hidden",
            "kind": "event",
            "normalized_text": "UNOPENED_SENTINEL eastern gate",
            "source_ids": ["source"],
            "incoming_refs": [],
            "outgoing_refs": [],
            "reveal_after_nodes": ["node_2"],
        },
    )
    locators = []
    known_size = 0
    for record in records:
        payload = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
        path = chunk_dir / f"{record['entry_id']}.json"
        path.write_bytes(payload)
        if record["entry_id"] == "known":
            known_size = len(payload)
        locators.append(
            {
                "entry_id": record["entry_id"],
                "tokens": ["eastern", "gate"],
                "reveal_after_nodes": record["reveal_after_nodes"],
                "path": f"chunks/{record['entry_id']}.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )
    (tmp_path / "index.json").write_text(json.dumps({"entries": locators}))
    return DirectoryKnowledgeSource(tmp_path), known_size


def test_directory_source_opens_only_revealed_bounded_chunks(tmp_path: Path) -> None:
    source, known_size = _source(tmp_path)

    read = source.read(
        query_tokens=frozenset({"eastern"}),
        max_records=8,
        max_excerpt_bytes=8192,
    )

    assert tuple(item.entry_id for item in read.excerpts) == ("known",)
    assert read.counters == KnowledgeReadCounters(known_size, 1, 1)
    assert "UNOPENED_SENTINEL" not in repr(read)


def test_directory_source_honors_zero_bounds_without_opening_chunks(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)

    read = source.read(query_tokens=frozenset({"eastern"}), max_records=0, max_excerpt_bytes=1)

    assert read == KnowledgeRead((), KnowledgeReadCounters())


def test_directory_source_rejects_content_hash_mismatch(tmp_path: Path) -> None:
    source, _ = _source(tmp_path)
    path = tmp_path / "chunks" / "known.json"
    payload = path.read_bytes()
    path.write_bytes(b"[" + payload[1:])

    try:
        source.read(entry_ids=frozenset({"known"}), max_records=1, max_excerpt_bytes=4096)
    except ValueError as exc:
        assert str(exc) == "KNOWLEDGE_CHUNK_HASH"
    else:
        raise AssertionError("corrupt knowledge chunk was accepted")


def test_retrieval_consumes_bounded_source_and_reports_its_io(tmp_path: Path) -> None:
    source, known_size = _source(tmp_path)

    result = retrieve_from_source(
        source,
        "eastern gate",
        frozenset(),
        source_record_budget=1,
        source_byte_budget=known_size,
    )

    assert tuple(hit.entry.entry_id for hit in result.hits) == ("known",)
    assert result.counters == KnowledgeReadCounters(known_size, 1, 1)


@pytest.mark.parametrize(
    ("field", "value"),
    (("path", "../escape.json"), ("tokens", ["gate", "eastern"]), ("sha256", "x" * 64)),
)
def test_directory_source_rejects_hostile_locator_before_chunk_io(
    tmp_path: Path, field: str, value: object
) -> None:
    _source(tmp_path)
    index_path = tmp_path / "index.json"
    index = json.loads(index_path.read_text())
    index["entries"][0][field] = value
    index_path.write_text(json.dumps(index))

    with pytest.raises(ValueError, match="KNOWLEDGE_INDEX_ENTRY"):
        DirectoryKnowledgeSource(tmp_path)


def test_directory_source_rejects_duplicate_ids(tmp_path: Path) -> None:
    _source(tmp_path)
    index_path = tmp_path / "index.json"
    index = json.loads(index_path.read_text())
    index["entries"].append(index["entries"][0])
    index_path.write_text(json.dumps(index))

    with pytest.raises(ValueError, match="KNOWLEDGE_INDEX_DUPLICATE_ID"):
        DirectoryKnowledgeSource(tmp_path)


def test_bounded_text_keeps_valid_unicode_prefix() -> None:
    from src.narrative.knowledge_source import bounded_normalized_text

    bounded = bounded_normalized_text("é" * 2048)

    assert len(bounded.encode("utf-8")) <= 2048
    assert bounded == "é" * 1024


def test_shared_v2_package_opens_one_bounded_chunk(tmp_path: Path) -> None:
    with zipfile.ZipFile("tests/fixtures/v2/complete.story") as archive:
        for name in archive.namelist():
            prefix = "narrative/knowledge/"
            if name.startswith(prefix):
                target = tmp_path / name.removeprefix(prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))

    read = DirectoryKnowledgeSource(tmp_path).read(
        query_tokens=frozenset({"eastern"}),
        visited_nodes=frozenset({"node_00000000000000000000000000000001"}),
        max_records=1,
        max_excerpt_bytes=8192,
    )

    assert tuple(item.entry_id for item in read.excerpts) == (
        "knowledge_00000000000000000000000000000001",
    )
    assert read.counters.chunks_opened == read.counters.records_decoded == 1


def test_shared_spoiler_catalog_keeps_hidden_chunks_physically_unopened(tmp_path: Path) -> None:
    catalog = json.loads(
        Path("tests/fixtures/gm_retrieval/spoiler_catalog.json").read_text()
    )
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    locators = []
    sizes: dict[str, int] = {}
    for record in catalog["entries"]:
        payload = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
        path = chunk_dir / f"{record['entry_id']}.json"
        path.write_bytes(payload)
        sizes[record["entry_id"]] = len(payload)
        tokens = sorted(
            set(record["normalized_text"].split())
            | set(record["entry_id"].replace("-", " ").split())
            | {
                token
                for source_id in record["source_ids"]
                for token in source_id.replace("-", " ").split()
            }
        )
        locators.append(
            {
                "entry_id": record["entry_id"],
                "tokens": tokens,
                "reveal_after_nodes": record["reveal_after_nodes"],
                "path": f"chunks/{record['entry_id']}.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )
    (tmp_path / "index.json").write_text(json.dumps({"entries": locators}))
    source = DirectoryKnowledgeSource(tmp_path)

    before = source.read(
        query_tokens=frozenset({"sentinellocaltext31d8"}),
        max_records=8,
        max_excerpt_bytes=8192,
    )
    assert before == KnowledgeRead((), KnowledgeReadCounters())

    after = source.read(
        query_tokens=frozenset({"sentinellocaltext31d8"}),
        visited_nodes=frozenset({"node_local_reveal"}),
        max_records=8,
        max_excerpt_bytes=8192,
    )
    assert tuple(item.entry_id for item in after.excerpts) == ("sentinel-local-id-31d8",)
    assert after.counters == KnowledgeReadCounters(
        sizes["sentinel-local-id-31d8"], 1, 1
    )
