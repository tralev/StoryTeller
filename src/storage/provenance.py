"""Artifact provenance — canonical artifact IDs, dependency graph, produced-by metadata.

Phase 5.6X: Answers "why does this artifact exist?" — which upstream artifacts
each artifact derives from, and which model + prompt version produced it.

The manifest carries a ``provenance`` section (see manifest.schema.json):

    provenance:
      inventory:   {artifact_key: artifact_id}         (X1)
      depends_on:  {artifact_key: [upstream ids]}      (X2)
      produced_by: {artifact_key: {model, model_hash,
                                   prompt_version}}    (X3)

This module is a leaf — it imports only stdlib, so any layer (package builder,
PackageAcceptance, GenerateStory) may import it without creating cycles.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# X1: Canonical artifact ID prefixes — MUST match each generation step's
# _make_artifact_id() so the manifest inventory agrees with the IDs the
# steps stamped on their StepOutputs.
# ─────────────────────────────────────────────────────────────────────

ID_PREFIXES: dict[str, str] = {
    "world_physical": "physical_",
    "world": "worldrepo_",
    "bible": "world_",
    "reconciliation": "reconcile_",
    "style_bible": "style_",
    "story": "story_",
    "graph": "graph_",
    "images": "img_",
    "midi": "mid_",
    "gm_index": "gmindex_",
    "narrative_project": "narrative_",
    "media_intents": "mediaintents_",
    "local_maps": "localmaps_",
    "media": "media_",
    "package_candidate": "packagecandidate_",
    "package_acceptance": "acceptance_",
    "packager": "package_",
}

# ─────────────────────────────────────────────────────────────────────
# X2: Canonical dependency graph — which upstream artifacts each artifact
# is derived from (Bible → Story → Graph → Assets/Index → Package).
# ─────────────────────────────────────────────────────────────────────

DEPENDENCIES: dict[str, list[str]] = {
    "world_physical": [],
    "world": ["world_physical"],
    "bible": ["world"],
    "reconciliation": ["world", "bible"],
    "narrative_project": ["world", "bible", "reconciliation", "story"],
    "media_intents": ["narrative_project"],
    "local_maps": ["world"],
    "media": ["narrative_project", "images", "midi"],
    "style_bible": ["world", "bible", "reconciliation"],
    "story": ["world", "bible", "reconciliation"],
    "graph": ["story"],
    # Legacy graph dependencies remain resolvable while production-v2 records
    # the committed project and refined intents.
    "images": ["graph", "narrative_project", "media_intents", "style_bible"],
    "midi": ["graph", "narrative_project", "media_intents"],
    # ``graph`` preserves the transitional standard-plan dependency; the
    # production plan supplies narrative_project/local_maps/media instead.
    "gm_index": ["world", "bible", "graph", "narrative_project", "local_maps", "media"],
    "package_candidate": ["world", "bible", "reconciliation", "style_bible", "narrative_project",
                          "media_intents", "images", "midi", "local_maps", "media", "gm_index"],
    "package_acceptance": ["package_candidate"],
    "packager": ["package_candidate", "package_acceptance"],
}

# ─────────────────────────────────────────────────────────────────────
# X3: Per-artifact producing model role + prompt-template step.
# ─────────────────────────────────────────────────────────────────────

#: Which models_used identity produces each artifact.
PRODUCING_MODEL: dict[str, str] = {
    "bible": "text_generator",
    "style_bible": "text_generator",
    "story": "text_generator",
    "graph": "text_generator",
    "images": "image_generator",
    "midi": "text_generator",  # ABC notation generated through the text model
    "gm_index": "deterministic",  # Indexer — no model involved
}

#: Which prompt_versions key applies to each artifact.
PRODUCING_PROMPT: dict[str, str] = {
    "bible": "world_builder",
    "style_bible": "style_bible",
    "story": "story_writer",
    "graph": "game_designer",
    "images": "art_director",
    "midi": "composer",
    "gm_index": "",
}


def artifact_id(key: str, data: Any) -> str:
    """Content-derived artifact ID for *key* over *data*.

    Same algorithm as every generation step's ``_make_artifact_id``:
    ``{prefix}_{sha256(json.dumps(data, sort_keys=True))[:8]}``.
    """
    prefix = ID_PREFIXES.get(key, f"{key}_")
    digest = hashlib.sha256(
        json.dumps(data, sort_keys=True).encode(),
    ).hexdigest()[:8]
    return f"{prefix}{digest}"


#: Operational per-node metadata keys stripped before ID computation.
#: The media aggregated dicts carry absolute file paths (image_path,
#: thumb_path, midi_path) that differ between output directories — they must
#: not influence the canonical artifact ID, otherwise two same-seed runs into
#: different output dirs would produce different manifest inventories.
_OPERATIONAL_PATH_KEYS = frozenset({"image_path", "thumb_path", "midi_path"})


def _strip_operational(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively drop operational path keys for canonical ID computation."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k in _OPERATIONAL_PATH_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = _strip_operational(v)
        else:
            out[k] = v
    return out


def build_inventory(outputs: dict[str, Any]) -> dict[str, str]:
    """Compute content-derived artifact IDs for artifacts present in *outputs*.

    Only dict artifacts are inventoried (binary media aggregated dicts are
    dicts too, so images/midi are included). Operational path metadata is
    stripped so IDs are stable across output directories (Phase 5.6D
    determinism).
    """
    inventory: dict[str, str] = {}
    for key in ID_PREFIXES:
        data = outputs.get(key)
        if isinstance(data, dict):
            inventory[key] = artifact_id(key, _strip_operational(data))
    return inventory


def build_depends_on(
    inventory: dict[str, str],
    dependencies: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Resolve each artifact's upstream dependency *IDs* from *inventory*.

    ``depends_on["story"]`` = ["world_<hash>"] — the ID of the exact bible
    artifact the story was generated from. Unresolvable dependencies (missing
    upstream) are skipped.
    """
    deps = dependencies or DEPENDENCIES
    depends: dict[str, list[str]] = {}
    for key, upstream_keys in deps.items():
        if key not in inventory:
            continue
        depends[key] = [
            inventory[up] for up in upstream_keys if up in inventory
        ]
    return depends


def build_produced_by(
    models_used: dict[str, str],
    prompt_versions: dict[str, str],
    model_hashes: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Map each artifact to the {model, model_hash, prompt_version} that produced it.

    ``model_hashes`` are the per-model FILE hashes computed by GenerateStory's
    run-fingerprint pass (avoids re-reading multi-GB GGUFs). When unavailable
    (e.g. unit tests), falls back to a hash of the model identity string.
    """
    produced_by: dict[str, dict[str, str]] = {}
    for key, model_key in PRODUCING_MODEL.items():
        if model_key == "deterministic":
            produced_by[key] = {
                "model": "deterministic",
                "model_hash": "-",
                "prompt_version": "v1",
            }
            continue
        model_identity = models_used.get(model_key, "unknown")
        file_hash = (model_hashes or {}).get(model_key, "")
        if not file_hash:
            file_hash = hashlib.sha256(model_identity.encode()).hexdigest()[:16]
        prompt_step = PRODUCING_PROMPT.get(key, "")
        produced_by[key] = {
            "model": model_identity,
            "model_hash": file_hash,
            "prompt_version": prompt_versions.get(prompt_step, "v1"),
        }
    return produced_by


def build_provenance(
    outputs: dict[str, Any],
    models_used: dict[str, str],
    prompt_versions: dict[str, str],
    model_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the full ``provenance`` manifest section (X1 + X2 + X3)."""
    inventory = build_inventory(outputs)
    return {
        "inventory": inventory,
        "depends_on": build_depends_on(inventory),
        "produced_by": build_produced_by(
            models_used, prompt_versions, model_hashes,
        ),
    }
