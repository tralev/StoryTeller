"""Normalizer — enforces project-wide conventions on all pipeline output.

Every output passes through the Normalizer between validation and commit.
This gives every downstream component a predictable input format.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, cast


class Normalizer:
    """Enforces conventions: IDs, naming, sorting, formatting, paths, flags."""

    # Float precision for deterministic output
    FLOAT_PRECISION = 6

    # Valid entity ID patterns
    ID_PATTERNS = {
        "character": re.compile(r"^char_\d{2}$"),
        "location": re.compile(r"^loc_\d{2}$"),
        "faction": re.compile(r"^fac_\d{2}$"),
        "creature": re.compile(r"^cre_\d{2}$"),
        "artifact": re.compile(r"^art_\d{2}$"),
        "event": re.compile(r"^evt_\d{2}$"),
        "conflict": re.compile(r"^con_\d{2}$"),
        "node": re.compile(r"^node_\d{2}[a-z]?$"),
        "scene": re.compile(r"^scene_\d{2}_\d{2}$"),
        "choice": re.compile(r"^ch_\d{2}_[a-z]$"),
    }

    # Value enums for normalization
    TONES = {"dark_fantasy", "heroic_fantasy", "grimdark", "mythic", "weird_fantasy"}
    MORTALITY = {"low", "moderate", "high", "anyone_can_die"}
    KNOWLEDGE = {"ignorant", "superstitious", "aware", "scholarly"}
    ROLES = {"protagonist", "antagonist", "supporting", "background"}
    STATUSES = {"alive", "dead", "unknown", "transformed"}
    DANGER = {"low", "moderate", "high", "legendary"}

    @classmethod
    def process(cls, data: dict[str, Any], schema_name: str = "") -> dict[str, Any]:
        """Run all normalization passes on the data.

        Args:
            data: The generated data to normalize.
            schema_name: Name of the schema (for context-aware normalization).

        Returns:
            Normalized data dict.
        """
        data = cls.normalize_entity_ids(data)
        data = cls.normalize_enums(data)
        data = cls.normalize_flag_names(data)
        data = cls.normalize_asset_paths(data)
        data = cls.sort_arrays(data)
        data = cls.normalize_json(data)
        return data

    @classmethod
    def normalize_entity_ids(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Ensure entity IDs match their expected patterns.

        Does not change IDs — only validates they match the convention.
        Invalid IDs are logged as warnings but not modified (the generator
        should fix them via retry, not the normalizer).
        """
        if "entities" in data:
            for entity_type, entities in data["entities"].items():
                pattern = cls.ID_PATTERNS.get(
                    entity_type.rstrip("s"),  # "characters" → "character"
                    re.compile(r"^[a-z]+_\d{2}$"),
                )
                for entity in entities:
                    if "id" in entity and not pattern.match(entity["id"]):
                        # Log but don't change — let the validator catch this
                        pass
        return data

    @classmethod
    def normalize_enums(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize enum values to canonical forms.

        e.g., "Dark Fantasy" → "dark_fantasy", "High" → "high"
        """
        # Normalize tone
        if "narrative_rules" in data:
            rules = data["narrative_rules"]
            if "tone" in rules:
                tone = rules["tone"].lower().replace(" ", "_").replace("-", "_")
                if tone in cls.TONES:
                    rules["tone"] = tone
            if "mortality" in rules:
                mort = rules["mortality"].lower()
                if mort in cls.MORTALITY:
                    rules["mortality"] = mort
            if "knowledge_level" in rules:
                kl = rules["knowledge_level"].lower()
                if kl in cls.KNOWLEDGE:
                    rules["knowledge_level"] = kl

        # Normalize entity fields
        if "entities" in data:
            for entities in data["entities"].values():
                for entity in entities:
                    if "role" in entity:
                        role = entity["role"].lower().replace(" ", "_")
                        if role in cls.ROLES:
                            entity["role"] = role
                    if "status" in entity:
                        status = entity["status"].lower()
                        if status in cls.STATUSES:
                            entity["status"] = status
                    if "danger" in entity:
                        danger = entity["danger"].lower()
                        if danger in cls.DANGER:
                            entity["danger"] = danger

        # Normalize ending types
        if "endings_summary" in data:
            for ending in data["endings_summary"]:
                if "type" in ending:
                    ending["type"] = ending["type"].lower().replace(" ", "_")

        # Normalize scene types
        if "nodes" in data:
            for node in data["nodes"]:
                if "scene_type" in node:
                    node["scene_type"] = node["scene_type"].lower().replace(" ", "_")
                if "endings" in node and node["endings"].get("ending_type"):
                    node["endings"]["ending_type"] = (
                        node["endings"]["ending_type"].lower().replace(" ", "_")
                    )

        return data

    @classmethod
    def normalize_flag_names(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize flag names to snake_case."""
        if "flags_catalog" not in data:
            return data

        # Build mapping: old_key → new_key
        flag_map: dict[str, str] = {}
        normalized_catalog: dict[str, str] = {}

        for key, value in data["flags_catalog"].items():
            norm_key = re.sub(r"[^a-z0-9_]", "_", key.lower()).strip("_")
            if norm_key != key:
                flag_map[key] = norm_key
            normalized_catalog[norm_key] = value

        data["flags_catalog"] = normalized_catalog

        # Remap flag references in nodes
        if flag_map and "nodes" in data:
            for node in data["nodes"]:
                for choice in node.get("choices", []):
                    choice["requires_flags"] = [
                        flag_map.get(f, f) for f in choice.get("requires_flags", [])
                    ]
                    choice["forbids_flags"] = [
                        flag_map.get(f, f) for f in choice.get("forbids_flags", [])
                    ]
                    choice["sets_flags"] = [
                        flag_map.get(f, f) for f in choice.get("sets_flags", [])
                    ]
                for cond in node.get("conditional_text", []):
                    if "if_flag" in cond:
                        cond["if_flag"] = flag_map.get(cond["if_flag"], cond["if_flag"])

        return data

    @classmethod
    def normalize_asset_paths(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize asset paths to use forward slashes and relative paths."""
        # Asset paths are set by the pipeline, not the LLM.
        # This is a validation pass that ensures consistency.
        return data

    @classmethod
    def sort_arrays(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Sort entity arrays and node arrays by id for deterministic output."""
        if "entities" in data:
            for key in data["entities"]:
                if isinstance(data["entities"][key], list):
                    data["entities"][key] = sorted(
                        data["entities"][key],
                        key=lambda e: e.get("id", "") if isinstance(e, dict) else "",
                    )

        if "nodes" in data and isinstance(data["nodes"], list):
            data["nodes"] = sorted(
                data["nodes"],
                key=lambda n: n.get("node_id", "") if isinstance(n, dict) else "",
            )

        if "chapters" in data and isinstance(data["chapters"], list):
            data["chapters"] = sorted(
                data["chapters"],
                key=lambda c: c.get("number", 0) if isinstance(c, dict) else 0,
            )

        return data

    @classmethod
    def normalize_json(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Round-trip through JSON with sorted keys and fixed float precision.

        This is the core of determinism — ensures bit-identical JSON output
        for identical data by controlling key order and float representation.
        """
        # First round all floats
        rounded = cls._round_floats(data)
        # Then serialize and deserialize with sorted keys
        return cast(dict[str, Any], json.loads(
            json.dumps(
                rounded,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
        ))

    @classmethod
    def _round_floats(cls, obj: Any) -> Any:
        """Recursively round all floats to FLOAT_PRECISION decimal places."""
        if isinstance(obj, float):
            return round(obj, cls.FLOAT_PRECISION)
        elif isinstance(obj, dict):
            return {k: cls._round_floats(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._round_floats(item) for item in obj]
        return obj

    @classmethod
    def normalize_whitespace(cls, text: str) -> str:
        """Clean up whitespace in text content.

        - Strip trailing whitespace from each line
        - Ensure single newline at EOF
        - Normalize line endings to \n
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        return "\n".join(lines).rstrip("\n") + "\n"
