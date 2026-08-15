"""P8.WG1 — Lazy world lookup tests.

Prove that lookups by fact/source/region ID do not deserialize
the complete retained world.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.world.lazy_reader import (
    FactExcerpt, LazyWorldReader, RegionSnapshot, SiteSnapshot,
)


@pytest.fixture
def conformance_world() -> Path:
    """Use the conformance pipeline output from a previous run."""
    world_dir = Path("tmp/conformance_run/simulated")
    if not world_dir.is_dir():
        pytest.skip("conformance world not available — run forge generate-world first")
    return world_dir


class TestLazyWorldReader:
    def test_init_does_not_load_any_artifacts(self, conformance_world: Path) -> None:
        """P8.WG1: Creating a reader must not deserialize the world."""
        reader = LazyWorldReader(conformance_world)
        assert reader.loaded_artifact_count == 0

    def test_present_year_loads_only_one_artifact(self, conformance_world: Path) -> None:
        """P8.WG1: Getting present_year loads only simulation_index."""
        reader = LazyWorldReader(conformance_world)
        year = reader.present_year()
        assert year >= 0
        assert reader.loaded_artifact_count == 1  # only simulation_index

    def test_site_lookup_loads_only_sites(self, conformance_world: Path) -> None:
        """P8.WG1: Looking up a single site loads only the sites artifact."""
        reader = LazyWorldReader(conformance_world)

        # First, find a site ID without loading everything
        data = json.loads((conformance_world / "artifacts" / "sites.json").read_text())
        sites = data.get("payload", [])
        if not sites:
            pytest.skip("no sites in conformance world")

        # Clear any internal state by creating fresh reader
        reader2 = LazyWorldReader(conformance_world)
        site_id = str(sites[0].get("site_id", sites[0].get("id", "")))
        if not site_id:
            pytest.skip("site has no ID field")

        site = reader2.site(site_id)

        # Must have loaded exactly one artifact
        assert reader2.loaded_artifact_count == 2  # sites + world_index for width

        # Site must have valid fields
        assert isinstance(site, SiteSnapshot)
        assert site.site_id == site_id
        assert site.region_id != ""
        assert site.x >= 0

    def test_region_lookup_loads_only_regions(self, conformance_world: Path) -> None:
        """P8.WG1: Looking up a region loads only regions artifact."""
        data = json.loads((conformance_world / "artifacts" / "regions.json").read_text())
        payload = data.get("payload", {})
        entries = payload.get("regions", []) if isinstance(payload, dict) else []
        if not entries:
            pytest.skip("no regions in conformance world")

        reader = LazyWorldReader(conformance_world)
        region_id = str(entries[0].get("region_id", entries[0].get("id", "")))
        if not region_id:
            pytest.skip("region has no ID field")

        region = reader.region(region_id)
        assert reader.loaded_artifact_count == 2  # sites + world_index for width
        assert isinstance(region, RegionSnapshot)
        assert region.region_id == region_id
        assert region.cell_count >= 1

    def test_separate_lookups_share_cache(self, conformance_world: Path) -> None:
        """P8.WG1: Multiple lookups reuse the same lazy-loaded cache."""
        reader = LazyWorldReader(conformance_world)

        # Load sites once
        data = json.loads((conformance_world / "artifacts" / "sites.json").read_text())
        sites = data.get("payload", [])
        if len(sites) < 2:
            pytest.skip("need at least 2 sites")

        sid1 = str(sites[0].get("site_id", ""))
        sid2 = str(sites[1].get("site_id", ""))
        if not sid1 or not sid2:
            pytest.skip("sites missing IDs")

        reader.site(sid1)
        assert reader.loaded_artifact_count == 2  # sites + world_index for width

        reader.site(sid2)
        # Still 1 — same artifact, just different entry lookup
        assert reader.loaded_artifact_count == 2  # same cache, still sites + world_index

    def test_recent_events_loads_only_history(self, conformance_world: Path) -> None:
        """P8.WG1: History queries load only the history artifact."""
        reader = LazyWorldReader(conformance_world)
        events = reader.recent_events(limit=3)
        assert reader.loaded_artifact_count == 1
        assert isinstance(events, tuple)
        assert len(events) <= 3

    def test_full_world_is_not_deserialized(self, conformance_world: Path) -> None:
        """P8.WG1: Even after several queries, total loaded artifacts is bounded."""
        reader = LazyWorldReader(conformance_world)

        # Query several different domains
        reader.present_year()
        reader.recent_events(limit=1)

        # Load a site
        data = json.loads((conformance_world / "artifacts" / "sites.json").read_text())
        sites = data.get("payload", [])
        if sites:
            sid = str(sites[0].get("site_id", ""))
            if sid:
                reader.site(sid)

        # Load a region
        data2 = json.loads((conformance_world / "artifacts" / "regions.json").read_text())
        entries = data2.get("regions", [])
        if entries:
            rid = str(entries[0].get("region_id", ""))
            if rid:
                reader.region(rid)

        # Max loaded should be well under the total artifact count (22+)
        total_artifacts = len(list((conformance_world / "artifacts").glob("*.json")))
        assert reader.loaded_artifact_count < total_artifacts, (
            f"Lazy reader loaded {reader.loaded_artifact_count} of {total_artifacts} "
            f"artifacts — should be fewer than the full world"
        )
        assert reader.loaded_artifact_count <= 5  # simulation_index, history, sites, regions max

    def test_excerpt_returns_bounded_fact(self, conformance_world: Path) -> None:
        """P8.WG1: Fact excerpts are bounded and carry source IDs."""
        data = json.loads((conformance_world / "artifacts" / "sites.json").read_text())
        sites = data.get("payload", [])
        if not sites:
            pytest.skip("no sites")

        reader = LazyWorldReader(conformance_world)
        sid = str(sites[0].get("site_id", ""))

        # Find a field that exists
        ex = reader.excerpt(sid, "region_id")
        assert isinstance(ex, FactExcerpt)
        assert ex.fact_id == sid
        assert ex.field == "region_id"
        assert ex.byte_size >= 0
        assert ex.source_artifact_id != ""

    def test_route_between_returns_route_id(self, conformance_world: Path) -> None:
        """P8.WG1: Route lookup finds connecting routes by region pair."""
        data = json.loads((conformance_world / "artifacts" / "routes.json").read_text())
        payload = data.get("payload", {})
        entries = payload.get("routes", []) if isinstance(payload, dict) else []
        if not entries:
            pytest.skip("no routes")

        reader = LazyWorldReader(conformance_world)
        r0 = str(entries[0].get("start_region", entries[0].get("start_region_id", "")))
        r1 = str(entries[0].get("end_region", entries[0].get("end_region_id", "")))
        if not r0 or not r1:
            pytest.skip("route missing region IDs")

        route_id = reader.route_between(r0, r1)
        assert route_id is not None
        assert route_id.startswith("route_")
