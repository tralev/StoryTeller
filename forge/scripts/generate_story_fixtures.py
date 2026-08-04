"""Generate canonical .story v1 test fixtures for cross-platform testing.

Phase 5.5K: Creates fixtures used by Python, Android, and iOS tests.
Run this script to regenerate fixtures after schema changes.

Usage:
    cd forge && PYTHONPATH=src .venv/bin/python scripts/generate_story_fixtures.py
"""

from __future__ import annotations

import json
import zipfile
import os
from pathlib import Path
from typing import Any


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "story_packages"


# ── Minimal valid node data ────────────────────────────────────────────────


def _minimal_bible() -> dict[str, Any]:
    return {
        "world_name": "Minimal World",
        "narrative_rules": {
            "tone": "dark_fantasy",
            "forbidden": [],
            "required_themes": ["safe_return"],
            "mortality": "low",
            "knowledge_level": "naive",
        },
        "entities": {
            "characters": [
                {
                    "id": "char_01", "name": "Hero", "aliases": [],
                    "description": "The protagonist.", "role": "protagonist",
                    "archetype": "hero", "motivation": "Survival",
                    "flaw": "None", "strength": "Courage",
                    "relationships": [],
                    "status": "alive", "nodes": ["node_01"],
                },
            ],
            "locations": [
                {
                    "id": "loc_01", "name": "Start Room", "aliases": [],
                    "description": "A simple room.", "type": "wilderness",
                    "mood": "neutral", "danger": "none",
                    "connected_to": [], "nodes": ["node_01"],
                },
            ],
            "factions": [],
            "creatures": [],
            "artifacts": [],
            "events": [],
        },
        "systems": {
            "magic": {"source": "None", "rules": [], "costs": [], "limitations": "None"},
            "politics": {"power_structure": "None", "conflicts": []},
            "religion": {"gods": [], "afterlife": "None"},
        },
    }


def _minimal_style_bible() -> dict[str, Any]:
    return {
        "art_style": {
            "palette": "grey",
            "lighting": "neutral",
            "composition": "centered",
            "linework": "simple",
            "mood": "neutral",
            "forbidden": [],
        },
        "character_design": {},
        "location_palettes": {},
    }


def _minimal_story() -> dict[str, Any]:
    return {
        "chapters": [
            {
                "number": 1,
                "title": "The Beginning",
                "summary": "A short chapter.",
                "scenes": [
                    {
                        "scene_id": "scene_01_01",
                        "text": "You stand at the entrance of a dark cave.",
                        "characters_present": ["char_01"],
                        "location": "loc_01",
                        "entities_referenced": [],
                        "word_count": 10,
                    }
                ],
            }
        ],
    }


def _minimal_graph_1_node() -> dict[str, Any]:
    return {
        "starting_node": "node_01",
        "nodes": [
            {
                "node_id": "node_01",
                "chapter": 1,
                "scene_type": "ending",
                "text": "You step into the cave and find peace.",
                "present_characters": ["char_01"],
                "present_location": "loc_01",
                "present_creatures": [],
                "mood": "peaceful",
                "image_prompt": "A dark cave entrance, simple",
                "music_tone": "peaceful",
                "choices": [],
                "endings": {"is_ending": True, "ending_type": "peaceful", "ending_title": "Peace"},
            },
        ],
    }


def _minimal_gm_index() -> dict[str, Any]:
    return {
        "keywords": {"hero": [{"id": "char_01", "type": "character", "score": 1.0}]},
        "entity_cache": {
            "char_01": {"id": "char_01", "name": "Hero", "type": "character",
                        "summary": "The protagonist.", "reveal_after_node": None},
        },
        "node_contexts": {
            "node_01": {"characters": ["char_01"], "locations": ["loc_01"],
                        "factions": [], "creatures": [], "artifacts": []},
        },
    }


def _complete_graph_15_nodes() -> dict[str, Any]:
    """Generate 15 nodes with a branching structure."""
    nodes: list[dict[str, Any]] = []
    for i in range(1, 16):
        nid = f"node_{i:02d}"
        is_ending = i >= 13
        choices: list[dict[str, Any]] = []
        if not is_ending:
            left = f"node_{(i+1):02d}"
            right = f"node_{(i+2):02d}" if i < 12 else f"node_{min(i+1, 15):02d}"
            choices = [
                {"choice_id": f"ch_{i}a", "choice_text": "Proceed carefully.",
                 "target_node": left, "sets_flags": [f"chose_{i}_left"]},
                {"choice_id": f"ch_{i}b", "choice_text": "Charge forward.",
                 "target_node": right, "sets_flags": [f"chose_{i}_right"]},
            ]

        nodes.append({
            "node_id": nid, "chapter": min((i-1)//5 + 1, 3), "scene_type": "exploration",
            "text": f"Scene {i}: You continue your journey through the salt wastes.",
            "present_characters": ["char_01"],
            "present_location": "loc_01",
            "present_creatures": [],
            "mood": "desolate",
            "image_prompt": f"A vast salt waste, scene {i}",
            "music_tone": "melancholy",
            "choices": choices,
            "endings": {"is_ending": is_ending,
                        "ending_type": "heroic" if not is_ending else "peaceful",
                        "ending_title": f"Ending {i}" if is_ending else ""},
        })

    return {
        "starting_node": "node_01",
        "nodes": nodes,
    }


# ── .story builder ──────────────────────────────────────────────────────────


def _write_story_zip(path: Path, bible: dict, style: dict, story: dict,
                     graph: dict, gm_index: dict, manifest: dict,
                     image_bytes: bytes | None = None,
                     midi_bytes: bytes | None = None) -> None:
    """Build a .story ZIP from individual artifacts."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Content files
        zf.writestr("content/bible.json", json.dumps(bible, indent=2, sort_keys=True))
        zf.writestr("content/style_bible.json", json.dumps(style, indent=2, sort_keys=True))
        zf.writestr("content/story.json", json.dumps(story, indent=2, sort_keys=True))
        zf.writestr("content/graph.json", json.dumps(graph, indent=2, sort_keys=True))
        zf.writestr("content/gm_index.json", json.dumps(gm_index, indent=2, sort_keys=True))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

        # Image files for nodes with image_prompt
        for node in graph.get("nodes", []):
            nid = node["node_id"]
            if node.get("image_prompt"):
                img = image_bytes or _minimal_png()
                zf.writestr(f"content/images/{nid}.png", img)
                zf.writestr(f"content/thumbnails/{nid}.png", img[:128])
            if node.get("music_tone"):
                midi = midi_bytes or _minimal_midi()
                zf.writestr(f"content/midi/{nid}.mid", midi)

        # Save directory
        zf.writestr("save/.gitkeep", "")


def _minimal_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _minimal_midi() -> bytes:
    return (
        b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x00\x80"
        b"MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
    )


def _build_manifest(
    title: str, seed: int, story_id: str, num_nodes: int,
    num_images: int, num_midi: int, schema_version: int = 1,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "artifact_id": f"fixture_{story_id}",
        "story_id": story_id,
        "title": title,
        "tone": "dark_fantasy",
        "seed": seed,
        "generated_at": "2026-08-04T12:00:00Z",
        "generator_version": "0.1.0",
        "models_used": {
            "text_generator": "qwen2.5-7b-instruct-Q4_K_M",
            "validator": "phi-3.5-mini-instruct-Q4_K_M",
            "image_generator": "sdxl-turbo-Q8_0",
            "music_generator": "via-text",
        },
        "prompt_versions": {
            "world_builder": "v1",
            "story_writer": "v1",
            "game_designer": "v1",
            "art_director": "v1",
            "composer": "v1",
            "style_bible": "v1",
        },
        "entry_point": "node_01",
        "files": {
            "bible": "content/bible.json",
            "style_bible": "content/style_bible.json",
            "story": "content/story.json",
            "graph": "content/graph.json",
            "gm_index": "content/gm_index.json",
            "images": "content/images/",
            "midi": "content/midi/",
            "thumbnails": "content/thumbnails/",
        },
        "stats": {
            "total_nodes": num_nodes,
            "total_images": num_images,
            "total_midi": num_midi,
            "total_endings": 1,
        },
        "content_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    }


# ── Valid fixtures ───────────────────────────────────────────────────────────


def generate_minimal_valid_1_node() -> None:
    """Minimal valid .story with a single node ending."""
    story_id = "00000000-0000-0000-0000-000000000001"
    bible = _minimal_bible()
    style = _minimal_style_bible()
    story = _minimal_story()
    graph = _minimal_graph_1_node()
    gm_index = _minimal_gm_index()
    manifest = _build_manifest("Minimal 1 Node", 1, story_id, 1, 1, 1)

    _write_story_zip(
        FIXTURES_DIR / "minimal_valid_1_node.story",
        bible, style, story, graph, gm_index, manifest,
    )


def generate_complete_15_nodes() -> None:
    """Complete .story with 15 nodes, images, and MIDI."""
    story_id = "00000000-0000-0000-0000-000000000002"
    bible = _minimal_bible()
    style = _minimal_style_bible()
    story = _minimal_story()
    graph = _complete_graph_15_nodes()
    gm_index = _minimal_gm_index()
    manifest = _build_manifest("Complete 15 Nodes", 2, story_id, 15, 15, 15)

    _write_story_zip(
        FIXTURES_DIR / "complete_15_nodes.story",
        bible, style, story, graph, gm_index, manifest,
    )


# ── Invalid fixtures ────────────────────────────────────────────────────────


def generate_invalid_missing_manifest() -> None:
    """Valid ZIP but no manifest.json entry."""
    path = FIXTURES_DIR / "invalid_missing_manifest.story"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content/bible.json", json.dumps(_minimal_bible()))
        zf.writestr("content/story.json", json.dumps(_minimal_story()))
        zf.writestr("content/graph.json", json.dumps(_minimal_graph_1_node()))
        zf.writestr("content/gm_index.json", json.dumps(_minimal_gm_index()))
        zf.writestr("save/.gitkeep", "")


def generate_invalid_bad_graph_ref() -> None:
    """Valid ZIP but manifest.entry_point references a missing node."""
    bible = _minimal_bible()
    style = _minimal_style_bible()
    story = _minimal_story()
    graph = _minimal_graph_1_node()
    gm_index = _minimal_gm_index()
    manifest = _build_manifest("Bad Graph Ref", 3,
                               "00000000-0000-0000-0000-000000000003", 1, 0, 0)
    manifest["entry_point"] = "node_nonexistent"  # broken ref

    _write_story_zip(FIXTURES_DIR / "invalid_bad_graph_ref.story",
                     bible, style, story, graph, gm_index, manifest)


def generate_invalid_path_traversal() -> None:
    """ZIP containing a path traversal entry."""
    path = FIXTURES_DIR / "invalid_path_traversal.story"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../etc/passwd", "malicious")
        zf.writestr("content/bible.json", json.dumps(_minimal_bible()))
        zf.writestr("content/story.json", json.dumps(_minimal_story()))
        zf.writestr("content/graph.json", json.dumps(_minimal_graph_1_node()))
        zf.writestr("content/gm_index.json", json.dumps(_minimal_gm_index()))
        zf.writestr("manifest.json", json.dumps(_build_manifest(
            "Path Traversal", 4, "00000000-0000-0000-0000-000000000004", 1, 0, 0,
        )))


def generate_invalid_unsupported_version() -> None:
    """Valid ZIP but schema_version = 99 (unsupported)."""
    bible = _minimal_bible()
    style = _minimal_style_bible()
    story = _minimal_story()
    graph = _minimal_graph_1_node()
    gm_index = _minimal_gm_index()
    manifest = _build_manifest("Unsupported Version", 5,
                               "00000000-0000-0000-0000-000000000005", 1, 0, 0,
                               schema_version=99)

    _write_story_zip(FIXTURES_DIR / "invalid_unsupported_version.story",
                     bible, style, story, graph, gm_index, manifest)


def generate_invalid_hash_mismatch() -> None:
    """Valid ZIP but manifest.content_hash doesn't match actual content."""
    bible = _minimal_bible()
    style = _minimal_style_bible()
    story = _minimal_story()
    graph = _minimal_graph_1_node()
    gm_index = _minimal_gm_index()
    manifest = _build_manifest("Hash Mismatch", 6,
                               "00000000-0000-0000-0000-000000000006", 1, 0, 0)
    manifest["content_hash"] = "deadbeef" * 8  # obviously wrong

    _write_story_zip(FIXTURES_DIR / "invalid_hash_mismatch.story",
                     bible, style, story, graph, gm_index, manifest)


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Generating .story fixtures in {FIXTURES_DIR}")

    # Valid fixtures
    generate_minimal_valid_1_node()
    print("  ✓ minimal_valid_1_node.story")

    generate_complete_15_nodes()
    print("  ✓ complete_15_nodes.story")

    # Invalid fixtures
    generate_invalid_missing_manifest()
    print("  ✓ invalid_missing_manifest.story")

    generate_invalid_bad_graph_ref()
    print("  ✓ invalid_bad_graph_ref.story")

    generate_invalid_path_traversal()
    print("  ✓ invalid_path_traversal.story")

    generate_invalid_unsupported_version()
    print("  ✓ invalid_unsupported_version.story")

    generate_invalid_hash_mismatch()
    print("  ✓ invalid_hash_mismatch.story")

    print(f"\nDone — {7} fixtures generated.")


if __name__ == "__main__":
    main()
