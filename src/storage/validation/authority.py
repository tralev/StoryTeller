"""Retained world, civilization, and narrative authority validation."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import PurePosixPath
from typing import Any, Mapping

from ...world.views import REQUIRED_KINDS
from .common import CanonicalEncoder, JsonLoader, PackageV2Error


def validate_civilization_references(
    archive: zipfile.ZipFile, load_json: JsonLoader
) -> None:
    regions = load_json(archive.read("world/regions.json"), "world/regions.json")
    sites = load_json(archive.read("world/sites.json"), "world/sites.json")
    languages = load_json(
        archive.read("world/source/identities.json"), "world/source/identities.json"
    )
    civilizations = load_json(
        archive.read("world/civilizations.json"), "world/civilizations.json"
    )
    region_ids = {item["region_id"] for item in regions["regions"]}
    site_ids = {item["site_id"] for item in sites["sites"]}
    payload = languages.get("payload", {})
    language_ids = {
        item.get("language_id")
        for item in payload.get("languages", [])
        if isinstance(item, dict)
    }
    records = civilizations.get("civilizations")
    if not isinstance(records, list) or not records:
        raise PackageV2Error(
            "PACKAGE_CIVILIZATION_REFERENCES", "civilizations are missing"
        )
    civilization_ids: set[str] = set()
    claimed: set[str] = set()
    for civilization in records:
        civilization_id = (
            civilization.get("civilization_id")
            if isinstance(civilization, dict)
            else None
        )
        territory = (
            civilization.get("territory") if isinstance(civilization, dict) else None
        )
        economy = (
            civilization.get("economy") if isinstance(civilization, dict) else None
        )
        if (
            not isinstance(civilization_id, str)
            or civilization_id in civilization_ids
            or civilization.get("capital_site_id") not in site_ids
            or civilization.get("language_id") not in language_ids
            or not isinstance(territory, list)
            or not territory
            or any(region not in region_ids or region in claimed for region in territory)
            or not isinstance(economy, dict)
            or any(type(value) is not int or value < 0 for value in economy.values())
            or type(civilization.get("population")) is not int
            or civilization["population"] < 0
        ):
            raise PackageV2Error(
                "PACKAGE_CIVILIZATION_REFERENCES",
                "civilization references are inconsistent",
            )
        civilization_ids.add(civilization_id)
        claimed.update(territory)


def validate_flat_world_domain(
    archive: zipfile.ZipFile,
    names: set[str],
    domain: str,
    source_name: str,
    load_json: JsonLoader,
    canonical_json: CanonicalEncoder,
) -> None:
    """Prove a reader-facing projection is the byte-exact source payload."""
    path = f"world/{domain}.json"
    source_path = f"world/source/{source_name}.json"
    if path not in names or source_path not in names:
        raise PackageV2Error(
            "PACKAGE_WORLD_FLAT_DOMAIN", f"{domain} projection missing", path
        )
    envelope = load_json(archive.read(source_path), source_path)
    if not isinstance(envelope, dict) or "payload" not in envelope:
        raise PackageV2Error(
            "PACKAGE_WORLD_FLAT_DOMAIN", "source envelope is malformed", source_path
        )
    if archive.read(path) != canonical_json(envelope["payload"]):
        raise PackageV2Error(
            "PACKAGE_WORLD_FLAT_DOMAIN",
            f"{domain} projection differs from source envelope",
            path,
        )


def validate_world_source_coverage(
    archive: zipfile.ZipFile, names: set[str], load_json: JsonLoader
) -> None:
    """Prove every declared authoritative envelope is retained byte-for-byte."""
    coverage_path = "world/source/coverage.json"
    if coverage_path not in names:
        raise PackageV2Error(
            "PACKAGE_WORLD_SOURCE_COVERAGE",
            "coverage ledger is missing",
            coverage_path,
        )
    ledger = load_json(archive.read(coverage_path), coverage_path)
    if (
        not isinstance(ledger, dict)
        or ledger.get("format") != "storyteller.world-source-coverage.v1"
        or ledger.get("required_domains") != sorted(REQUIRED_KINDS)
        or not isinstance(ledger.get("sources"), list)
    ):
        raise PackageV2Error(
            "PACKAGE_WORLD_SOURCE_COVERAGE",
            "coverage ledger shape is invalid",
            coverage_path,
        )
    source_names = {
        name
        for name in names
        if name.startswith("world/source/")
        and name.endswith(".json")
        and name != coverage_path
    }
    rows = ledger["sources"]
    row_paths = [row.get("archive_path") for row in rows if isinstance(row, dict)]
    if len(row_paths) != len(set(row_paths)) or set(row_paths) != source_names:
        raise PackageV2Error(
            "PACKAGE_WORLD_SOURCE_COVERAGE",
            "ledger must cover every source member exactly once",
            coverage_path,
        )
    index = load_json(archive.read("world/index.json"), "world/index.json")
    domains = index.get("domains") if isinstance(index, dict) else None
    if not isinstance(domains, list) or set(domains) != {
        PurePosixPath(path).stem for path in source_names
    }:
        raise PackageV2Error(
            "PACKAGE_WORLD_SOURCE_COVERAGE",
            "world index domains differ from retained sources",
            "world/index.json",
        )
    if not set(REQUIRED_KINDS) <= set(domains):
        raise PackageV2Error(
            "PACKAGE_WORLD_SOURCE_COVERAGE",
            "required authoritative domain is missing",
            "world/index.json",
        )
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "source_name",
            "archive_path",
            "artifact_id",
            "sha256",
            "size_bytes",
            "retention",
        }:
            raise PackageV2Error(
                "PACKAGE_WORLD_SOURCE_COVERAGE", "source row is invalid", coverage_path
            )
        path = row["archive_path"]
        data = archive.read(path)
        envelope = load_json(data, path)
        if (
            row["source_name"] != PurePosixPath(path).stem
            or row["retention"] != "byte_for_byte"
            or row["size_bytes"] != len(data)
            or row["sha256"] != hashlib.sha256(data).hexdigest()
            or not isinstance(envelope, dict)
            or row["artifact_id"] != envelope.get("artifact_id")
        ):
            raise PackageV2Error(
                "PACKAGE_WORLD_SOURCE_COVERAGE",
                "source bytes or identity differ from ledger",
                path,
            )


def validate_narrative_authority(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    load_json: JsonLoader,
) -> None:
    bible_data = archive.read("narrative/bible.json")
    reconciliation_data = archive.read("narrative/reconciliation.json")
    bible = load_json(bible_data, "narrative/bible.json")
    reconciliation = load_json(
        reconciliation_data, "narrative/reconciliation.json"
    )
    story = load_json(archive.read("narrative/story.json"), "narrative/story.json")
    coverage = load_json(
        archive.read("world/source/coverage.json"), "world/source/coverage.json"
    )
    source_rows = {
        row["source_name"]: row
        for row in coverage.get("sources", [])
        if isinstance(row, dict) and isinstance(row.get("source_name"), str)
    }
    expected_ids = reconciliation.get("world_artifact_ids")
    expected_hashes = reconciliation.get("world_file_hashes")
    authority_valid = False
    if (
        isinstance(expected_ids, dict)
        and isinstance(expected_hashes, dict)
        and set(expected_ids) == set(expected_hashes)
    ):
        if expected_ids and all(name.startswith("world/") for name in expected_ids):
            world_rows = {
                row["path"]: row
                for row in manifest["artifacts"]
                if row["path"].startswith("world/")
            }
            authority_valid = expected_ids == {
                path: row["artifact_id"] for path, row in world_rows.items()
            } and expected_hashes == {
                path: row["sha256"] for path, row in world_rows.items()
            }
        else:
            authority_valid = (
                all(name in source_rows for name in expected_ids)
                and all(
                    source_rows[name].get("artifact_id") == artifact_id
                    for name, artifact_id in expected_ids.items()
                )
                and all(
                    source_rows[name].get("sha256") == expected_hashes[name]
                    for name in expected_hashes
                )
            )
    if not authority_valid:
        raise PackageV2Error(
            "PACKAGE_RECONCILIATION_INPUTS", "reconciliation world inputs differ"
        )
    if bible.get("authoritative_refs") != sorted(expected_ids.values()):
        raise PackageV2Error(
            "PACKAGE_BIBLE_AUTHORITY", "Bible authority inventory differs"
        )
    if (
        reconciliation.get("accepted") is not True
        or type(reconciliation.get("ruleset_version")) is not int
        or reconciliation["ruleset_version"] < 1
        or not isinstance(reconciliation.get("issues"), list)
        or any(
            issue.get("severity") in {"error", "fatal"}
            for issue in reconciliation["issues"]
            if isinstance(issue, dict)
        )
        or story.get("bible_hash") != hashlib.sha256(bible_data).hexdigest()
        or story.get("reconciliation_hash")
        != hashlib.sha256(reconciliation_data).hexdigest()
    ):
        raise PackageV2Error(
            "PACKAGE_RECONCILIATION_INPUTS",
            "reconciliation or narrative hashes differ",
        )
    regions = {item["region_id"] for item in bible.get("regions", [])}
    civilizations = {
        item["civilization_id"] for item in bible.get("civilizations", [])
    }
    history_index = load_json(
        archive.read("world/history/index.json"), "world/history/index.json"
    )
    events = {PurePosixPath(path).stem for path in history_index["events"]}
    settlements_source = load_json(
        archive.read("world/source/settlements.json"),
        "world/source/settlements.json",
    )
    settlements = {
        item["settlement_id"]
        for item in settlements_source.get("payload", [])
        if isinstance(item, dict) and isinstance(item.get("settlement_id"), str)
    }
    if (
        any(item.get("region_id") not in regions for item in bible.get("sites", []))
        or any(
            region not in regions
            for item in bible.get("civilizations", [])
            for region in item.get("territory", [])
        )
        or any(
            item.get("civilization_id") not in civilizations
            or item.get("settlement_id") not in settlements
            for item in bible.get("people", [])
        )
        or any(
            cause not in events
            for item in bible.get("history", [])
            for cause in item.get("causes", [])
        )
        or any(
            participant not in civilizations
            for item in bible.get("history", [])
            for participant in item.get("participants", [])
        )
    ):
        raise PackageV2Error(
            "PACKAGE_REFERENCE_RESOLUTION", "Bible reference is unresolved"
        )
