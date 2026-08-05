"""Validated, hashed builtin simulation registries."""
from __future__ import annotations

import hashlib

from ..artifacts import canonical_json

BUILTINS: dict[str, tuple[dict[str, object], ...]] = {
    "people": ({"id": "people_human", "needs": ("grain", "shelter")},
               {"id": "people_dwarf", "needs": ("grain", "materials")}),
    "governments": ({"id": "council", "stability_ppm": 650_000},
                    {"id": "monarchy", "stability_ppm": 700_000},
                    {"id": "clan_compact", "stability_ppm": 600_000}),
    "materials": ({"id": "grain", "renewable": True}, {"id": "timber", "renewable": True},
                  {"id": "stone", "renewable": False}, {"id": "iron", "renewable": False}),
    "recipes": ({"id": "food", "input": "grain", "output": "food", "ratio_ppm": 800_000},),
    "species": ({"id": "pack_animal", "role": "transport"}, {"id": "crop", "role": "food"}),
    "supernatural": ({"id": "resonance", "cost": "fatigue", "prohibited": ("create_matter", "resurrection")},),
}


def validate_and_hash_registries() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, entries in sorted(BUILTINS.items()):
        ids = [str(entry["id"]) for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError(f"WG-REGISTRY-DUPLICATE: {name}")
        for entry in entries:
            ratio = entry.get("ratio_ppm")
            if ratio is not None and (not isinstance(ratio, int) or not 0 < ratio <= 1_000_000):
                raise ValueError(f"WG-REGISTRY-BALANCE: {entry['id']}")
        hashes[name] = hashlib.sha256(canonical_json(entries)).hexdigest()
    return hashes
