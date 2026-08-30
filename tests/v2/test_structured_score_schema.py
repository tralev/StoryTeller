import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

from src.narrative.media import generate_score
from src.storage.v2_schemas import draft202012_validator


def _production_score() -> dict[str, object]:
    score = generate_score(
        17,
        90,
        "node_00000000000000000000000000000001",
        ("region_00000000000000000000000000000001",),
        "a" * 64,
    )
    return cast(dict[str, object], json.loads(json.dumps(asdict(score))))


def test_production_score_satisfies_frozen_schema() -> None:
    schema = json.loads(Path("schemas/v2/structured-score.schema.json").read_text())
    assert list(draft202012_validator(schema).iter_errors(_production_score())) == []


def test_score_schema_rejects_empty_maps_sources_and_track_events() -> None:
    schema = json.loads(Path("schemas/v2/structured-score.schema.json").read_text())
    validator = draft202012_validator(schema)
    valid = _production_score()
    mutations = []
    for field in ("tempo_map", "time_signature_map", "key_signature_map", "source_ids"):
        changed = copy.deepcopy(valid)
        changed[field] = []
        mutations.append(changed)
    changed = copy.deepcopy(valid)
    changed["tracks"][0]["events"] = []  # type: ignore[index]
    mutations.append(changed)

    assert all(list(validator.iter_errors(document)) for document in mutations)
