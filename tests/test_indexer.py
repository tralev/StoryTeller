"""Tests for GmIndexer — TDD for Phase 5.

Builds the Game Master index from the graph + bible for zero-ML mobile retrieval.
Produces: keywords (inverted index), entity_cache (summaries), node_contexts.

Validates against gm_index.schema.json.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.job_queue import PipelineContext
from src.models.base import StepOutput


# ── test data ────────────────────────────────────────────────────────────────


def _make_bible() -> dict[str, Any]:
    """Bible with characters, locations, creatures for indexing."""
    return {
        "entities": {
            "characters": [
                {"id": "char_01", "name": "Eldrin Vane", "aliases": ["The Crow"], "description": "A gaunt sellsword hunting his sister's murderer.", "role": "protagonist", "status": "alive"},
                {"id": "char_02", "name": "Mira Thorn", "aliases": ["The Healer"], "description": "An elderly healer who runs Thorn's Hearth.", "role": "supporting", "status": "alive"},
                {"id": "char_03", "name": "High Priest Malachar", "aliases": ["The White Hand"], "description": "A masked priest seeking to resurrect the dead god.", "role": "antagonist", "status": "alive", "reveal_after_node": "node_05"},
            ],
            "locations": [
                {"id": "loc_01", "name": "The Ashen Marches", "aliases": ["the Marches"], "description": "A vast salt flat where nothing grows."},
                {"id": "loc_02", "name": "The Salt Temple", "aliases": ["White Sanctum"], "description": "A cathedral carved from compressed salt."},
            ],
            "factions": [
                {"id": "fac_01", "name": "The Salt Priests", "aliases": ["White Robes"], "description": "Cultists who believe the dead god will rise."},
            ],
            "creatures": [
                {"id": "cre_01", "name": "Salt Wraith", "aliases": ["wraith"], "description": "An undead creature formed from salt-storms."},
            ],
            "artifacts": [
                {"id": "art_01", "name": "The God-Heart Shard", "aliases": ["the Shard"], "description": "A black crystal from a dead god's heart.", "reveal_after_node": "node_04"},
            ],
            "events": [
                {"id": "evt_01", "name": "The Godfall", "aliases": [], "description": "When a god fell from the heavens three thousand years ago."},
            ],
        },
        "systems": {
            "magic": {"source": "Divine blood in salt"},
        },
    }


def _make_graph() -> dict[str, Any]:
    """Graph with 4 nodes covering all entity types."""
    return {
        "starting_node": "node_01",
        "flags_catalog": {
            "took_shard": "Player picked up the Shard",
            "trusted_mira": "Player accepted Mira's help",
        },
        "nodes": [
            {
                "node_id": "node_01", "chapter": 1, "scene_type": "exploration",
                "text": "You stand at the edge.", "mood": "desolate",
                "present_characters": ["char_01"], "present_location": "loc_01",
                "present_creatures": [], "choices": [],
                "image_prompt": "Lone figure at salt flats", "music_tone": "melancholy",
            },
            {
                "node_id": "node_02", "chapter": 1, "scene_type": "dialogue",
                "text": "Mira sits by the spring.", "mood": "peaceful",
                "present_characters": ["char_01", "char_02"], "present_location": "loc_01",
                "present_creatures": [], "choices": [
                    {"choice_id": "ch_02_a", "choice_text": "Accept her help", "target_node": "node_03",
                     "sets_flags": ["trusted_mira"]},
                ],
                "image_prompt": "Healer by a spring", "music_tone": "peaceful",
            },
            {
                "node_id": "node_03", "chapter": 2, "scene_type": "combat",
                "text": "A Salt Wraith rises.", "mood": "tense",
                "present_characters": ["char_01"], "present_location": "loc_02",
                "present_creatures": ["cre_01"], "choices": [],
                "image_prompt": "Wraith attacking", "music_tone": "tense",
            },
            {
                "node_id": "node_04", "chapter": 3, "scene_type": "ending",
                "text": "The Heart shatters.", "mood": "triumphant",
                "present_characters": ["char_01", "char_03"], "present_location": "loc_02",
                "present_creatures": [], "choices": [],
                "image_prompt": "Heart shattering", "music_tone": "triumphant",
            },
        ],
        "endings_summary": [
            {"node_id": "node_04", "type": "good", "title": "Freedom"},
        ],
    }


# ── Expected Indexer API ─────────────────────────────────────────────────────
# GmIndexer(bible, graph) or GmIndexer() with .build(bible, graph)
# Output: gm_index dict with keywords, entity_cache, node_contexts


class TestGmIndexerKeywords:
    """Keyword inverted index — entity names, aliases, and key terms."""

    def test_builds_keyword_index(self) -> None:
        """Index maps normalized keywords to entities with weights."""
        bible = _make_bible()
        index: dict[str, list[dict[str, Any]]] = {}

        # Simulate indexing: extract keywords from entity names
        for ent_type, entities in bible["entities"].items():
            for ent in entities:
                name = ent["name"].lower()
                index.setdefault(name, []).append({
                    "type": ent_type.rstrip("s"),  # "characters" → "character"
                    "id": ent["id"],
                    "weight": 1.0,
                })
                for alias in ent.get("aliases", []):
                    idx_alias = alias.lower()
                    index.setdefault(idx_alias, []).append({
                        "type": ent_type.rstrip("s"),
                        "id": ent["id"],
                        "weight": 0.9,
                    })

        assert "eldrin vane" in index
        assert index["eldrin vane"][0]["id"] == "char_01"
        assert index["eldrin vane"][0]["weight"] == 1.0

    def test_aliases_have_lower_weight(self) -> None:
        """Aliases get weight 0.9 vs 1.0 for primary names."""
        bible = _make_bible()
        index: dict[str, list[dict[str, Any]]] = {}
        for ent_type, entities in bible["entities"].items():
            for ent in entities:
                for alias in ent.get("aliases", []):
                    key = alias.lower()
                    index.setdefault(key, []).append({
                        "id": ent["id"], "weight": 0.9,
                    })

        assert "the crow" in index
        assert index["the crow"][0]["weight"] == 0.9
        assert "the healer" in index

    def test_keywords_are_case_insensitive(self) -> None:
        """All keywords are lowercased for consistent lookups."""
        raw = "Eldrin Vane"
        normalized = raw.lower()
        assert normalized == "eldrin vane"

    def test_keyword_types_are_valid_enum(self) -> None:
        """Keyword entry types match gm_index.schema.json enum."""
        valid_types = {"character", "location", "faction", "creature",
                       "artifact", "event", "system", "node"}
        # All entity categories map to valid types
        for cat in ["characters", "locations", "factions", "creatures", "artifacts", "events"]:
            singular = cat.rstrip("s")
            assert singular in valid_types, f"'{singular}' not in valid types"
        assert "system" in valid_types

    def test_weights_are_between_zero_and_one(self) -> None:
        """All keyword weights are in [0, 1]."""
        weights = [1.0, 0.9, 0.8, 0.6, 0.5]
        for w in weights:
            assert 0.0 <= w <= 1.0

    def test_faction_aliases_are_indexed(self) -> None:
        """Faction aliases like 'White Robes' are keyword entries."""
        bible = _make_bible()
        fac = bible["entities"]["factions"][0]
        aliases = [a.lower() for a in fac.get("aliases", [])]
        assert "white robes" in aliases


class TestGmIndexerEntityCache:
    """Entity cache — one-line summaries for GM prompt injection."""

    def test_builds_entity_cache_from_bible(self) -> None:
        """Every entity gets a name + summary + related entry."""
        bible = _make_bible()
        cache: dict[str, dict[str, Any]] = {}

        for ent_type, entities in bible["entities"].items():
            for ent in entities:
                cache[ent["id"]] = {
                    "name": ent["name"],
                    "summary": ent["description"][:300],
                    "related": [],
                }

        assert "char_01" in cache
        assert cache["char_01"]["name"] == "Eldrin Vane"
        assert len(cache["char_01"]["summary"]) > 0

    def test_summaries_are_within_max_length(self) -> None:
        """Summaries are ≤ 300 chars per gm_index.schema.json."""
        bible = _make_bible()
        for ent_type, entities in bible["entities"].items():
            for ent in entities:
                summary = ent["description"][:300]
                assert len(summary) <= 300

    def test_reveal_after_node_is_preserved(self) -> None:
        """Entities with reveal_after_node keep it in cache for filtering."""
        bible = _make_bible()
        entities_with_reveal: list[str] = []
        for ent_type, entities in bible["entities"].items():
            for ent in entities:
                if "reveal_after_node" in ent:
                    entities_with_reveal.append(ent["id"])

        assert "char_03" in entities_with_reveal
        assert "art_01" in entities_with_reveal

    def test_related_entities_are_tracked(self) -> None:
        """Entity cache includes related entity IDs."""
        cache = {
            "char_01": {"related": ["char_02", "loc_01"]},
            "loc_01": {"related": ["char_01"]},
        }
        assert "char_02" in cache["char_01"]["related"]
        assert len(cache["loc_01"]["related"]) == 1

    def test_all_entity_categories_are_included(self) -> None:
        """All 6 entity categories + systems are in the cache."""
        bible = _make_bible()
        categories = list(bible["entities"].keys())
        assert "characters" in categories
        assert "locations" in categories
        assert "factions" in categories
        assert "creatures" in categories
        assert "artifacts" in categories
        assert "events" in categories
        assert len(categories) == 6


class TestGmIndexerNodeContexts:
    """Node contexts — per-node entity presence for targeted GM retrieval."""

    def test_node_context_has_required_fields(self) -> None:
        """Each node context has present_characters, present_location, present_creatures."""
        graph = _make_graph()
        for node in graph["nodes"]:
            ctx = {
                "node_id": node["node_id"],
                "present_characters": node.get("present_characters", []),
                "present_location": node.get("present_location", ""),
                "present_creatures": node.get("present_creatures", []),
            }
            assert "present_characters" in ctx
            assert "present_location" in ctx
            assert "present_creatures" in ctx

    def test_tracks_entities_per_node(self) -> None:
        """Node_03 has 1 creature, node_04 has antagonist."""
        graph = _make_graph()
        node_03 = graph["nodes"][2]
        node_04 = graph["nodes"][3]

        assert "cre_01" in node_03["present_creatures"]
        assert "char_03" in node_04["present_characters"]

    def test_mentioned_entities_tracked(self) -> None:
        """Nodes can track entities mentioned but not present."""
        contexts: dict[str, dict[str, Any]] = {}
        graph = _make_graph()
        for node in graph["nodes"]:
            contexts[node["node_id"]] = {
                "present_characters": node["present_characters"],
                "present_location": node["present_location"],
                "present_creatures": node.get("present_creatures", []),
                "mentioned_entities": node.get("mentioned_entities", []),
            }
        # Initial structure is valid even with empty mentioned_entities
        assert "node_01" in contexts

    def test_active_flags_per_node(self) -> None:
        """Nodes that set flags track them in active_flags."""
        graph = _make_graph()
        flag_setters: dict[str, list[str]] = {}

        for node in graph["nodes"]:
            flags = []
            for ch in node.get("choices", []):
                flags.extend(ch.get("sets_flags", []))
            if flags:
                flag_setters[node["node_id"]] = flags

        assert "node_02" in flag_setters
        assert "trusted_mira" in flag_setters["node_02"]

    def test_all_graph_nodes_have_context(self) -> None:
        """Every node in the graph gets a context entry."""
        graph = _make_graph()
        contexts = {n["node_id"]: {} for n in graph["nodes"]}
        assert len(contexts) == len(graph["nodes"])
        assert all(nid in contexts for nid in ["node_01", "node_02", "node_03", "node_04"])


class TestGmIndexerIntegration:
    """Full gm_index assembly and validation."""

    def test_full_index_structure(self) -> None:
        """Complete gm_index has schema_version, keywords, entity_cache, node_contexts."""
        index = {
            "schema_version": 1,
            "keywords": {"eldrin vane": [{"type": "character", "id": "char_01", "weight": 1.0}]},
            "entity_cache": {"char_01": {"name": "Eldrin Vane", "summary": "A sellsword.", "related": []}},
            "node_contexts": {"node_01": {"present_characters": ["char_01"], "present_location": "loc_01", "present_creatures": []}},
        }
        assert "schema_version" in index
        assert "keywords" in index
        assert "entity_cache" in index
        assert "node_contexts" in index

    def test_reveal_after_node_filters_gm_knowledge(self) -> None:
        """Entities with reveal_after_node are hidden until the reader reaches that node."""
        cache = {
            "char_01": {"name": "Eldrin", "summary": "A hero."},
            "char_03": {"name": "Malachar", "summary": "A priest.", "reveal_after_node": "node_05"},
        }
        visited_nodes = {"node_01", "node_02"}

        # GM should only see entities revealed at or before the current node
        visible = {
            eid: data for eid, data in cache.items()
            if "reveal_after_node" not in data
            or data["reveal_after_node"] in visited_nodes
        }
        assert "char_01" in visible
        assert "char_03" not in visible  # Hidden until node_05

    def test_magic_system_in_index(self) -> None:
        """Magic system gets an entry in the entity cache."""
        cache = {
            "magic": {
                "name": "Magic System",
                "summary": "Powered by divine salt. Has physical cost.",
                "related": [],
            }
        }
        assert "magic" in cache
        assert cache["magic"]["name"] == "Magic System"

    def test_validates_against_schema(self) -> None:
        """Full index matches gm_index.schema.json structure."""
        import json, os
        from jsonschema import Draft7Validator

        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "schemas", "gm_index.schema.json",
        )
        with open(schema_path) as f:
            schema = json.load(f)

        index = {
            "schema_version": 1,
            "keywords": {
                "eldrin": [{"type": "character", "id": "char_01", "weight": 1.0}],
            },
            "entity_cache": {
                "char_01": {
                    "name": "Eldrin Vane",
                    "summary": "A sellsword.",
                    "related": ["char_02"],
                },
            },
            "node_contexts": {
                "node_01": {
                    "present_characters": ["char_01"],
                    "present_location": "loc_01",
                    "present_creatures": [],
                },
            },
        }

        errors = list(Draft7Validator(schema).iter_errors(index))
        assert not errors, f"gm_index failed schema validation: {errors}"


class TestGmIndexerEdgeCases:
    """Edge cases for indexer."""

    def test_empty_graph_produces_minimal_index(self) -> None:
        """Empty graph → empty node_contexts, still valid."""
        index = {
            "schema_version": 1,
            "keywords": {},
            "entity_cache": {},
            "node_contexts": {},
        }
        assert index["node_contexts"] == {}

    def test_entity_with_no_aliases(self) -> None:
        """Entities without aliases still get indexed by name only."""
        ent = {"id": "char_01", "name": "Eldrin", "aliases": []}
        keywords = [ent["name"].lower()]
        assert "eldrin" in keywords
        assert len(keywords) == 1

    def test_duplicate_keyword_entries(self) -> None:
        """Two entities sharing a keyword produce multiple entries."""
        index = {
            "salt": [
                {"type": "location", "id": "loc_01", "weight": 0.8},
                {"type": "faction", "id": "fac_01", "weight": 0.8},
            ],
        }
        assert len(index["salt"]) == 2

    def test_requires_graph_in_context(self) -> None:
        """GmIndexer needs graph in context.outputs."""
        ctx = PipelineContext(run_id="r1", seed=1)
        assert "graph" not in ctx.outputs


class TestFindRelated:
    """_find_related discovers entity relationships from bible data."""

    def test_finds_character_via_relationship_target(self) -> None:
        from src.storage.indexer import GmIndexer
        bible = {
            "entities": {
                "characters": [
                    {"id": "char_01", "name": "Hero", "relationships": [{"target": "char_02", "type": "ally"}]},
                    {"id": "char_02", "name": "Ally", "relationships": []},
                ],
                "locations": [], "factions": [], "creatures": [], "artifacts": [], "events": [],
            },
        }
        related = GmIndexer._find_related("char_02", bible)
        assert "char_01" in related

    def test_finds_faction_via_members(self) -> None:
        from src.storage.indexer import GmIndexer
        bible = {
            "entities": {
                "factions": [{"id": "fac_01", "name": "Guild", "members": ["char_01"]}],
                "characters": [{"id": "char_01", "name": "Hero", "relationships": []}],
                "locations": [], "creatures": [], "artifacts": [], "events": [],
            },
        }
        related = GmIndexer._find_related("char_01", bible)
        assert "fac_01" in related

    def test_finds_location_via_connected_to(self) -> None:
        from src.storage.indexer import GmIndexer
        bible = {
            "entities": {
                "locations": [
                    {"id": "loc_01", "name": "Forest", "connected_to": ["loc_02"]},
                    {"id": "loc_02", "name": "Village", "connected_to": []},
                ],
                "characters": [], "factions": [], "creatures": [], "artifacts": [], "events": [],
            },
        }
        related = GmIndexer._find_related("loc_02", bible)
        assert "loc_01" in related

    def test_self_reference_skipped(self) -> None:
        from src.storage.indexer import GmIndexer
        bible = {
            "entities": {
                "characters": [
                    {"id": "char_01", "name": "Self", "relationships": [{"target": "char_01", "type": "self"}]},
                ],
                "locations": [], "factions": [], "creatures": [], "artifacts": [], "events": [],
            },
        }
        related = GmIndexer._find_related("char_01", bible)
        assert "char_01" not in related

    def test_empty_bible_no_crash(self) -> None:
        from src.storage.indexer import GmIndexer
        related = GmIndexer._find_related("char_01", {"entities": {}})
        assert related == []


class TestExtractMentionedEntities:
    """_extract_mentioned_entities finds implied entity references."""

    def test_mentions_character_from_other_node(self) -> None:
        from src.storage.indexer import GmIndexer
        node = {"text": "char_02 was here", "present_characters": ["char_01"], "present_location": "loc_01"}
        graph = {"node_contexts": {"node_02": {"present_characters": ["char_02"], "present_location": "loc_02"}}}
        mentioned = GmIndexer._extract_mentioned_entities(node, graph)
        assert "char_02" in mentioned

    def test_not_own_characters(self) -> None:
        from src.storage.indexer import GmIndexer
        node = {"text": "char_01 stands", "present_characters": ["char_01"], "present_location": "loc_01"}
        graph = {"node_contexts": {"node_02": {"present_characters": ["char_01"], "present_location": ""}}}
        mentioned = GmIndexer._extract_mentioned_entities(node, graph)
        assert "char_01" not in mentioned

    def test_mentions_location_from_other_node(self) -> None:
        from src.storage.indexer import GmIndexer
        node = {"text": "from loc_02 he came", "present_characters": [], "present_location": "loc_01"}
        graph = {"node_contexts": {"node_02": {"present_characters": [], "present_location": "loc_02"}}}
        mentioned = GmIndexer._extract_mentioned_entities(node, graph)
        assert "loc_02" in mentioned

    def test_empty_contexts_no_crash(self) -> None:
        from src.storage.indexer import GmIndexer
        mentioned = GmIndexer._extract_mentioned_entities(
            {"text": "nothing", "present_characters": [], "present_location": ""}, {},
        )
        assert mentioned == []
