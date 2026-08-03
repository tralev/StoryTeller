"""Extended Normalizer tests — entity ID warnings, asset path normalization."""

from __future__ import annotations

import warnings

import pytest

from src.normalizer import Normalizer


class TestEntityIdWarnings:
    """Normalizer warns on entity ID pattern mismatches."""

    def test_warns_on_invalid_character_id(self) -> None:
        """Invalid character ID pattern triggers a warning."""
        data = {
            "entities": {
                "characters": [
                    {"id": "BAD_FORMAT", "name": "Test"},
                    {"id": "char_01", "name": "Valid"},
                ]
            }
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Normalizer.normalize_entity_ids(data)
            assert len(w) == 1
            assert "BAD_FORMAT" in str(w[0].message)
            assert "char_" in str(w[0].message)

    def test_no_warning_on_valid_ids(self) -> None:
        """Valid entity IDs produce no warnings."""
        data = {
            "entities": {
                "characters": [{"id": "char_01"}, {"id": "char_02"}],
                "locations": [{"id": "loc_01"}],
                "factions": [{"id": "fac_01"}],
                "creatures": [{"id": "cre_01"}],
                "artifacts": [{"id": "art_01"}],
                "events": [{"id": "evt_01"}],
            }
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Normalizer.normalize_entity_ids(data)
            assert len(w) == 0

    def test_warns_per_invalid_entity(self) -> None:
        """Each invalid ID produces its own warning."""
        data = {
            "entities": {
                "characters": [
                    {"id": "bad_1"},
                    {"id": "bad_2"},
                ]
            }
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Normalizer.normalize_entity_ids(data)
            assert len(w) == 2


class TestAssetPathNormalization:
    """Normalizer cleans up asset paths."""

    def test_backslashes_become_forward_slashes(self) -> None:
        data = {"nodes": [{"image": "images\\node_01.png"}]}
        result = Normalizer.normalize_asset_paths(data)
        assert "\\" not in result["nodes"][0]["image"]

    def test_adds_content_prefix(self) -> None:
        data = {"nodes": [{"image": "images/node_01.png"}]}
        result = Normalizer.normalize_asset_paths(data)
        assert result["nodes"][0]["image"] == "content/images/node_01.png"

    def test_no_double_content_prefix(self) -> None:
        data = {"nodes": [{"image": "content/images/node_01.png"}]}
        result = Normalizer.normalize_asset_paths(data)
        assert result["nodes"][0]["image"] == "content/images/node_01.png"

    def test_collapses_double_slashes(self) -> None:
        data = {"nodes": [{"image": "content//images//node_01.png"}]}
        result = Normalizer.normalize_asset_paths(data)
        assert "//" not in result["nodes"][0]["image"]

    def test_normalizes_music_paths_too(self) -> None:
        data = {"nodes": [{"music": "midi/scene_01.mid"}]}
        result = Normalizer.normalize_asset_paths(data)
        assert result["nodes"][0]["music"] == "content/midi/scene_01.mid"

    def test_normalizes_thumbnail_paths(self) -> None:
        data = {"nodes": [{"thumbnail": "thumbnails/node_01.png"}]}
        result = Normalizer.normalize_asset_paths(data)
        assert result["nodes"][0]["thumbnail"] == "content/thumbnails/node_01.png"

    def test_no_nodes_no_error(self) -> None:
        """Data without nodes is returned unchanged."""
        data = {"something": "else"}
        result = Normalizer.normalize_asset_paths(data)
        assert result == data
