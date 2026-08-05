import json
from pathlib import Path

from jsonschema.validators import validator_for


def test_all_v2_schemas_are_draft_2020_12() -> None:
    paths = sorted(Path("schemas/v2").glob("*.schema.json"))
    assert len(paths) >= 20
    for path in paths:
        schema = json.loads(path.read_bytes())
        assert schema["$schema"].endswith("2020-12/schema")
        validator_for(schema).check_schema(schema)
