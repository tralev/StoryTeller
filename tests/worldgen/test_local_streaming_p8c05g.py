"""P8.C05G lazy local chunk access, resume, corruption, and budget evidence."""

from __future__ import annotations

import json

import pytest

from src.narrative.pipeline import generate_narrative_local_maps
from src.worldgen.local_index import local_world_index_from_mapping
from src.worldgen.local_reader import LazyLocalWorldReader, audit_local_storage


def test_lazy_reader_loads_only_requested_members_with_bounded_cache(phase5_project) -> None:
    _, _, project = phase5_project
    reader = LazyLocalWorldReader(project, cache_entries=2)
    first, second = reader.index.entries[:2]
    reader.map(first.site_id)
    reader.chunk(first.site_id, "material", first.material_chunk_hashes[0])
    reads = reader.disk_reads
    reader.chunk(first.site_id, "material", first.material_chunk_hashes[0])
    assert reader.disk_reads == reads
    reader.map(second.site_id)
    assert reader.cached_entry_count == 2
    assert reader.cached_entry_count < len(reader.index.entries)


def test_local_publication_resumes_and_repairs_corrupt_chunk(tmp_path, phase4_world) -> None:
    first = generate_narrative_local_maps(phase4_world, tmp_path)
    assert first["published"] > 0 and first["reused"] == 0
    second = generate_narrative_local_maps(phase4_world, tmp_path)
    assert second["published"] == 0
    assert second["reused"] == first["published"]

    index = local_world_index_from_mapping(json.loads((tmp_path / "local_index.json").read_text()))
    entry = index.entries[0]
    chunk = (
        tmp_path
        / "local_chunks"
        / entry.site_id
        / "material"
        / f"{entry.material_chunk_hashes[0]}.json"
    )
    chunk.write_bytes(b"corrupt")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        audit_local_storage(tmp_path, index)
    repaired = generate_narrative_local_maps(phase4_world, tmp_path)
    assert repaired["published"] == 1
    assert repaired["reused"] == first["published"] - 1
    audit_local_storage(tmp_path, index)


def test_local_storage_audit_reports_complete_bounded_inventory(phase5_project) -> None:
    _, _, project = phase5_project
    index = local_world_index_from_mapping(json.loads((project / "local_index.json").read_text()))
    report = audit_local_storage(project, index)
    assert report["site_count"] == len(index.sites)
    assert report["chunk_count"] > report["site_count"]
    assert report["total_bytes"] > 0
    assert report["total_bytes"] <= report["total_budget_bytes"]
    assert report["max_cache_entries"] == 1
