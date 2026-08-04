"""GmIndexer — builds the Game Master index for zero-ML mobile retrieval.

Takes a graph + bible and produces a gm_index.json with:
  keywords — inverted index (name/alias → entity refs with weights)
  entity_cache — one-line summaries for every entity
  node_contexts — per-node present characters, location, creatures

The App A Game Master uses this for targeted context injection without
running a vector database on the phone.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, cast

from ..job_queue import PipelineContext
from ..models.base import StepOutput


class GmIndexer:
    """Build the Game Master index from graph + bible.

    Usage:
        indexer = GmIndexer()
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["graph"] = {...}
        context.outputs["bible"] = {...}
        output = await indexer.run(context)
        # output.data is the gm_index dict
    """

    async def run(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        graph = context.outputs.get_graph()  # Phase 5.6N N5
        bible = context.outputs.get_bible()
        if graph is None:
            raise ValueError("GmIndexer requires context.outputs['graph']")
        if bible is None:
            raise ValueError("GmIndexer requires context.outputs['bible']")

        # Phase 5.6N N5: TypedDict artifacts are cast to plain dicts at the
        # internal-helper boundary (JSON dicts at runtime).
        bible_d: dict[str, Any] = cast(dict[str, Any], bible)
        graph_d: dict[str, Any] = cast(dict[str, Any], graph)
        keywords = self._build_keywords(bible_d, graph_d)
        entity_cache = self._build_entity_cache(bible_d)
        node_contexts = self._build_node_contexts(graph_d)

        index: dict[str, Any] = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "seed": context.seed,
            "keywords": keywords,
            "entity_cache": entity_cache,
            "node_contexts": node_contexts,
        }

        digest = hashlib.sha256(
            json.dumps(index, sort_keys=True).encode()
        ).hexdigest()[:8]
        return StepOutput(data=index, step_name="indexer", artifact_id=f"gmindex_{digest}")

    # ── keywords ────────────────────────────────────────────────────────

    def _build_keywords(
        self, bible: dict[str, Any], graph: dict[str, Any]
    ) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}

        for cat, entities in bible.get("entities", {}).items():
            ent_type = cat.rstrip("s")  # "characters" → "character"
            for ent in entities:
                eid = ent.get("id", "?")
                # Primary name → weight 1.0
                name = ent.get("name", "")
                if name:
                    key = name.lower()
                    index.setdefault(key, []).append(
                        {"type": ent_type, "id": eid, "weight": 1.0}
                    )
                # Aliases → weight 0.9
                for alias in ent.get("aliases", []):
                    key = alias.lower()
                    index.setdefault(key, []).append(
                        {"type": ent_type, "id": eid, "weight": 0.9}
                    )
                # Extract keywords from description (weight 0.5)
                desc = ent.get("description", "")
                if desc:
                    words = re.findall(r"[a-zA-Z]{3,}", desc.lower())
                    for word in set(words):
                        # Avoid duplicates with name/alias
                        if word not in index:
                            index.setdefault(word, []).append(
                                {"type": ent_type, "id": eid, "weight": 0.5}
                            )

        # Magic system keyword
        magic = bible.get("systems", {}).get("magic", {})
        if magic:
            index.setdefault("magic", []).append(
                {"type": "system", "id": "magic", "weight": 1.0}
            )

        # Node keywords from titles/descriptions
        for node in graph.get("nodes", []):
            nid = node.get("node_id", "?")
            index.setdefault(nid, []).append(
                {"type": "node", "id": nid, "weight": 1.0}
            )

        return index

    # ── entity cache ────────────────────────────────────────────────────

    def _build_entity_cache(self, bible: dict[str, Any]) -> dict[str, dict[str, Any]]:
        cache: dict[str, dict[str, Any]] = {}
        for cat, entities in bible.get("entities", {}).items():
            for ent in entities:
                eid = ent.get("id", "?")
                entry: dict[str, Any] = {
                    "name": ent.get("name", "Unknown"),
                    "summary": ent.get("description", "")[:300],
                    "related": self._find_related(eid, bible),
                }
                if "reveal_after_node" in ent:
                    entry["reveal_after_node"] = ent["reveal_after_node"]
                cache[eid] = entry

        # Magic system
        magic = bible.get("systems", {}).get("magic", {})
        if magic:
            cache["magic"] = {
                "name": "Magic System",
                "summary": (
                    f"Source: {magic.get('source', '?')}. "
                    f"Limitations: {magic.get('limitations', '?')}"
                )[:300],
                "related": [],
            }

        return cache

    @staticmethod
    def _find_related(entity_id: str, bible: dict[str, Any]) -> list[str]:
        """Find entities that reference this ID in their fields."""
        related: list[str] = []
        for cat, entities in bible.get("entities", {}).items():
            for ent in entities:
                eid = ent.get("id", "")
                if eid == entity_id:
                    continue
                # Check relationships field (characters)
                for rel in ent.get("relationships", []):
                    if rel.get("target") == entity_id and eid not in related:
                        related.append(eid)
                # Check connected_to (locations)
                if entity_id in ent.get("connected_to", []):
                    if eid not in related:
                        related.append(eid)
                # Check members (factions)
                if entity_id in ent.get("members", []):
                    if eid not in related:
                        related.append(eid)
        return related

    # ── node contexts ───────────────────────────────────────────────────

    def _build_node_contexts(
        self, graph: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        contexts: dict[str, dict[str, Any]] = {}
        for node in graph.get("nodes", []):
            nid = node.get("node_id", "?")
            # Collect mentioned entities from text
            mentioned = self._extract_mentioned_entities(node, graph)
            # Collect flags from choices
            flags: list[str] = []
            for ch in node.get("choices", []):
                flags.extend(ch.get("sets_flags", []))
            contexts[nid] = {
                "present_characters": node.get("present_characters", []),
                "present_location": node.get("present_location", ""),
                "present_creatures": node.get("present_creatures", []),
                "mentioned_entities": mentioned,
                "active_flags": flags,
            }
        return contexts

    @staticmethod
    def _extract_mentioned_entities(
        node: dict[str, Any], graph: dict[str, Any]
    ) -> list[str]:
        """Find entity IDs mentioned in node text but not in present_*."""
        mentioned: list[str] = []
        text = node.get("text", "").lower()
        # Check conditional_text for entity references
        for ct in node.get("conditional_text", []):
            text += " " + ct.get("append", "").lower()

        present_chars = set(node.get("present_characters", []))
        present_loc = node.get("present_location", "")

        # Scan: check if entity IDs from present or location appear in text
        # but are not listed in present_characters (implied appearances)
        for nid, ctx in graph.get("node_contexts", {}).items():
            if not isinstance(ctx, dict):
                continue
            for cid in ctx.get("present_characters", []):
                cid_lower = cid.lower()
                if cid_lower in text and cid not in present_chars and cid not in mentioned:
                    mentioned.append(cid)
            loc = ctx.get("present_location", "")
            if loc and loc.lower() in text and loc != present_loc and loc not in mentioned:
                mentioned.append(loc)

        return mentioned
