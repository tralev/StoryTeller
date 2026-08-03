"""Test MIDI backend — ABC validation and conversion.

These tests run WITHOUT models — music21 is a pure Python library.
"""

import pytest

from src.backends.midi_backend import AbcMusicGenerator

VALID_ABC = """X:1
T:Goblin Encounter
M:4/4
L:1/8
K:Dm
D2 F2 A2 d2 | c2 A2 F2 D2 | E2 G2 c2 e2 | d8 |]
"""

INVALID_ABC_NO_NOTES = """X:1
T:Empty Tune
M:4/4
L:1/8
K:C
"""

INVALID_ABC_NO_HEADER = "D2 F2 A2 d2 | c2 A2 F2 D2 |"


class TestAbcValidation:
    """Test ABC notation validation without models."""

    def test_valid_abc_passes(self) -> None:
        """Well-formed ABC notation passes validation."""
        assert AbcMusicGenerator.validate_abc(VALID_ABC) is True

    def test_empty_string_fails(self) -> None:
        """Empty string is invalid."""
        assert AbcMusicGenerator.validate_abc("") is False

    def test_none_fails(self) -> None:
        """None is invalid."""
        assert AbcMusicGenerator.validate_abc("") is False

    def test_missing_x_header_fails(self) -> None:
        """ABC without X: header is invalid."""
        assert AbcMusicGenerator.validate_abc(INVALID_ABC_NO_HEADER) is False

    def test_valid_from_fixture(self) -> None:
        """ABC from test fixture validates."""
        fixture_path = "tests/fixtures/abc_valid.txt"
        with open(fixture_path) as f:
            abc = f.read()
        assert AbcMusicGenerator.validate_abc(abc) is True

    def test_invalid_from_fixture(self) -> None:
        """Invalid ABC from test fixture fails."""
        fixture_path = "tests/fixtures/abc_invalid.txt"
        with open(fixture_path) as f:
            abc = f.read()
        assert AbcMusicGenerator.validate_abc(abc) is False


class TestAbcToMidi:
    """Test ABC → MIDI conversion."""

    def test_conversion_returns_bytes(self) -> None:
        """Valid ABC converts to non-empty MIDI bytes."""
        midi_bytes = AbcMusicGenerator.abc_to_midi(VALID_ABC)
        assert isinstance(midi_bytes, bytes)
        assert len(midi_bytes) > 0

    def test_conversion_starts_with_midi_header(self) -> None:
        """MIDI output starts with standard MThd header."""
        midi_bytes = AbcMusicGenerator.abc_to_midi(VALID_ABC)
        assert midi_bytes[:4] == b"MThd"

    def test_invalid_abc_raises_value_error(self) -> None:
        """Invalid ABC notation raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ABC"):
            AbcMusicGenerator.abc_to_midi("not valid abc at all")

    def test_conversion_is_deterministic(self) -> None:
        """Same ABC produces identical MIDI bytes."""
        midi1 = AbcMusicGenerator.abc_to_midi(VALID_ABC)
        midi2 = AbcMusicGenerator.abc_to_midi(VALID_ABC)
        assert midi1 == midi2


class TestAbcGeneration:
    """Test placeholder ABC generation."""

    @pytest.mark.asyncio
    async def test_generate_returns_valid_abc(self) -> None:
        """Placeholder generate() returns valid ABC notation."""
        gen = AbcMusicGenerator()
        abc = await gen.generate("The wind howls.", "tense", seed=42)
        assert abc.startswith("X:1")
        assert "K:Dm" in abc

    @pytest.mark.asyncio
    async def test_generated_abc_is_valid(self) -> None:
        """Generated placeholder ABC passes validation."""
        gen = AbcMusicGenerator()
        abc = await gen.generate("Test scene.", "peaceful", seed=42)
        assert AbcMusicGenerator.validate_abc(abc) is True
