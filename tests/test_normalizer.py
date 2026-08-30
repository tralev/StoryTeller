"""Test the Normalizer — enforces project-wide conventions."""

from src.normalizer import Normalizer


class TestEnumNormalization:
    """Normalizer canonicalizes enum values."""

    def test_normalize_tone(self) -> None:
        """Tone is normalized to snake_case."""
        data = {"narrative_rules": {"tone": "Dark Fantasy"}}
        result = Normalizer.normalize_enums(data)
        assert result["narrative_rules"]["tone"] == "dark_fantasy"

    def test_normalize_tone_with_hyphens(self) -> None:
        """Hyphenated tone is normalized."""
        data = {"narrative_rules": {"tone": "dark-fantasy"}}
        result = Normalizer.normalize_enums(data)
        assert result["narrative_rules"]["tone"] == "dark_fantasy"

    def test_normalize_mortality(self) -> None:
        """Mortality is lowercased."""
        data = {"narrative_rules": {"mortality": "HIGH"}}
        result = Normalizer.normalize_enums(data)
        assert result["narrative_rules"]["mortality"] == "high"

    def test_normalize_knowledge_level(self) -> None:
        """Knowledge level is lowercased."""
        data = {"narrative_rules": {"knowledge_level": "Scholarly"}}
        result = Normalizer.normalize_enums(data)
        assert result["narrative_rules"]["knowledge_level"] == "scholarly"

    def test_normalize_character_role(self) -> None:
        """Character role is normalized (valid roles get canonical form)."""
        data = {"entities": {"characters": [{"role": "Protagonist"}]}}
        result = Normalizer.normalize_enums(data)
        assert result["entities"]["characters"][0]["role"] == "protagonist"

    def test_normalize_character_status(self) -> None:
        """Character status is lowercased."""
        data = {"entities": {"characters": [{"status": "ALIVE"}]}}
        result = Normalizer.normalize_enums(data)
        assert result["entities"]["characters"][0]["status"] == "alive"

    def test_normalize_ending_type(self) -> None:
        """Ending type is normalized."""
        data = {"endings_summary": [{"type": "Bitter Sweet"}]}
        result = Normalizer.normalize_enums(data)
        assert result["endings_summary"][0]["type"] == "bitter_sweet"

    def test_normalize_scene_type(self) -> None:
        """Scene type in nodes is normalized."""
        data = {"nodes": [{"scene_type": "Dark Fantasy"}]}
        result = Normalizer.normalize_enums(data)
        assert result["nodes"][0]["scene_type"] == "dark_fantasy"


class TestSortArrays:
    """Normalizer sorts arrays by id for deterministic output."""

    def test_sort_characters_by_id(self) -> None:
        """Characters are sorted by id."""
        data = {
            "entities": {
                "characters": [
                    {"id": "char_03", "name": "C"},
                    {"id": "char_01", "name": "A"},
                    {"id": "char_02", "name": "B"},
                ]
            }
        }
        result = Normalizer.sort_arrays(data)
        ids = [c["id"] for c in result["entities"]["characters"]]
        assert ids == ["char_01", "char_02", "char_03"]

    def test_sort_nodes_by_id(self) -> None:
        """Nodes are sorted by node_id."""
        data = {
            "nodes": [
                {"node_id": "node_03"},
                {"node_id": "node_01"},
                {"node_id": "node_02"},
            ]
        }
        result = Normalizer.sort_arrays(data)
        ids = [n["node_id"] for n in result["nodes"]]
        assert ids == ["node_01", "node_02", "node_03"]

    def test_sort_chapters_by_number(self) -> None:
        """Chapters are sorted by number."""
        data = {
            "chapters": [
                {"number": 3, "title": "End"},
                {"number": 1, "title": "Start"},
                {"number": 2, "title": "Middle"},
            ]
        }
        result = Normalizer.sort_arrays(data)
        nums = [c["number"] for c in result["chapters"]]
        assert nums == [1, 2, 3]

    def test_preserves_non_entity_data(self) -> None:
        """Non-array, non-entity fields are untouched."""
        data = {"world_name": "Test World", "entities": {}}
        result = Normalizer.sort_arrays(data)
        assert result["world_name"] == "Test World"


class TestFlagNormalization:
    """Normalizer enforces snake_case flag names."""

    def test_normalize_flag_catalog_keys(self) -> None:
        """Flag catalog keys become snake_case."""
        data = {
            "flags_catalog": {
                "Took Shard": "Player took the shard",
                "trusted-priest": "Trusted the priest",
            }
        }
        result = Normalizer.normalize_flag_names(data)
        assert "took_shard" in result["flags_catalog"]
        assert "trusted_priest" in result["flags_catalog"]

    def test_normalize_flag_references_in_choices(self) -> None:
        """Flag references in choices are updated to match normalized keys."""
        data = {
            "flags_catalog": {
                "Took-Shard!": "Player took the shard",
            },
            "nodes": [
                {
                    "node_id": "node_01",
                    "choices": [
                        {
                            "sets_flags": ["Took-Shard!"],
                            "requires_flags": ["Took-Shard!"],
                        }
                    ],
                    "conditional_text": [],
                }
            ],
        }
        result = Normalizer.normalize_flag_names(data)
        assert result["nodes"][0]["choices"][0]["sets_flags"] == ["took_shard"]

    def test_no_change_when_already_normalized(self) -> None:
        """Already-normalized flags are unchanged."""
        data = {"flags_catalog": {"took_shard": "desc"}}
        result = Normalizer.normalize_flag_names(data)
        assert "took_shard" in result["flags_catalog"]


class TestJsonNormalization:
    """Normalizer ensures deterministic JSON output."""

    def test_sorted_keys(self) -> None:
        """JSON output has sorted keys."""
        data = {"z": 1, "a": 2, "m": 3}
        result = Normalizer.normalize_json(data)
        keys = list(result.keys())
        assert keys == ["a", "m", "z"]

    def test_fixed_float_precision(self) -> None:
        """Floats are rounded to 6 decimal places."""
        data = {"value": 3.141592653589793}
        result = Normalizer.normalize_json(data)
        # Should be rounded to 6 decimal places
        assert result["value"] == 3.141593

    def test_roundtrip_is_stable(self) -> None:
        """Multiple normalizations produce identical output."""
        data = {"b": 1, "a": 2, "c": 3.123456789}
        first = Normalizer.normalize_json(data)
        second = Normalizer.normalize_json(first)
        assert first == second

    def test_nested_objects(self) -> None:
        """Nested objects have sorted keys too."""
        data = {"outer": {"z": 1, "a": 2}}
        result = Normalizer.normalize_json(data)
        assert list(result.keys()) == ["outer"]
        assert list(result["outer"].keys()) == ["a", "z"]


class TestWhitespace:
    """Normalizer cleans up whitespace."""

    def test_strip_trailing(self) -> None:
        """Trailing whitespace is removed from each line."""
        text = "line one   \nline two  \n"
        result = Normalizer.normalize_whitespace(text)
        assert "   " not in result

    def test_crlf_to_lf(self) -> None:
        """CRLF line endings become LF."""
        text = "line one\r\nline two\r\n"
        result = Normalizer.normalize_whitespace(text)
        assert "\r" not in result

    def test_ends_with_newline(self) -> None:
        """Trailing newline is preserved when present in input."""
        text_with = "line one\nline two\n"
        result = Normalizer.normalize_whitespace(text_with)
        assert result.endswith("\n")

    def test_no_trailing_newline_when_input_lacks_one(self) -> None:
        """No trailing newline is added if input doesn't have one."""
        text_without = "line one\nline two"
        result = Normalizer.normalize_whitespace(text_without)
        assert not result.endswith("\n")
        assert result == "line one\nline two"
        assert not result.endswith("\n\n")


class TestProcess:
    """Full process() pipeline."""

    def test_process_runs_all_passes(self) -> None:
        """process() applies all normalizations."""
        data = {
            "narrative_rules": {"tone": "DARK-FANTASY"},
            "entities": {
                "characters": [
                    {"id": "char_02", "role": "Reluctant Hero"},
                    {"id": "char_01", "role": "Wise Healer"},
                ]
            },
        }
        result = Normalizer.process(data)
        assert result["narrative_rules"]["tone"] == "dark_fantasy"
        ids = [c["id"] for c in result["entities"]["characters"]]
        assert ids == ["char_01", "char_02"]

    def test_process_idempotent(self) -> None:
        """Running process() twice produces identical output."""
        data = {
            "narrative_rules": {"tone": "Dark Fantasy"},
            "entities": {"characters": [{"id": "char_02"}, {"id": "char_01"}]},
        }
        first = Normalizer.process(data)
        second = Normalizer.process(first)
        assert first == second
