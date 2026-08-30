"""Regression coverage for bounded recovery of structured model output."""

import pytest
from jsonschema import ValidationError

from src.backends.llm_backend import LlamaCppTextGenerator, _parse_json


def test_parser_uses_corrected_object_after_malformed_draft() -> None:
    raw = (
        '{"interpretations": ["unfinished"}\n'
        "] summary discarded by the model\n"
        '{"interpretations": ["A complete and authoritative interpretation."]}'
    )

    assert _parse_json(raw, "test://corrected") == {
        "interpretations": ["A complete and authoritative interpretation."]
    }


def test_parser_prefers_schema_valid_candidate_over_larger_invalid_one() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    raw = 'draft: {"name": 123, "extra": "field", "more": "stuff"} corrected: {"name": "ok"}'

    assert _parse_json(raw, "test://schema-preferred", schema=schema) == {"name": "ok"}
    # Without a schema the largest parseable candidate still wins, unchanged.
    assert _parse_json(raw, "test://no-schema") == {
        "name": 123,
        "extra": "field",
        "more": "stuff",
    }


def test_parser_falls_back_to_best_effort_when_nothing_validates() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }

    assert _parse_json('{"name": 123}', "test://no-valid-candidate", schema=schema) == {
        "name": 123,
    }


def test_text_backend_keeps_inference_grammar_free_under_memory_cap() -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def create_completion(self, **kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {"choices": [{"text": '{"value":"bounded"}'}]}

    backend = object.__new__(LlamaCppTextGenerator)
    backend._model = FakeModel()
    raw = backend._generate_text(
        "return JSON",
        temperature=0.1,
        seed=7,
        max_tokens=32,
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["value"],
            "properties": {"value": {"type": "string"}},
        },
    )

    assert raw == '{"value":"bounded"}'
    assert "grammar" not in captured


@pytest.mark.asyncio
async def test_text_backend_enforces_exact_schema_after_generation() -> None:
    class FakeModel:
        def create_completion(self, **kwargs: object) -> dict[str, object]:
            return {"choices": [{"text": '{"unexpected":true}'}]}

    backend = object.__new__(LlamaCppTextGenerator)
    backend._model = FakeModel()
    backend._total_calls = 0
    backend.model_name = "fake"
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["value"],
        "properties": {"value": {"type": "string"}},
    }

    with pytest.raises(ValidationError):
        await backend.generate("return JSON", schema=schema)
