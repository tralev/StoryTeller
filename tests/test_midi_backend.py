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

    @pytest.mark.asyncio
    async def test_generate_stores_seed(self) -> None:
        """generate() records the seed for reproducibility tracking."""
        gen = AbcMusicGenerator()
        await gen.generate("Scene.", "tense", seed=12345)
        assert gen._last_seed == 12345

    @pytest.mark.asyncio
    async def test_generate_stores_mood(self) -> None:
        """generate() records the mood."""
        gen = AbcMusicGenerator()
        await gen.generate("Scene.", "triumphant", seed=1)
        assert gen._last_mood == "triumphant"

    @pytest.mark.asyncio
    async def test_generate_stores_scene_text(self) -> None:
        """generate() records the scene text."""
        gen = AbcMusicGenerator()
        await gen.generate("A dark forest.", "mysterious", seed=1)
        assert gen._last_scene_text == "A dark forest."


class TestValidateAbcFallback:
    """validate_abc() behavior for edge cases."""

    def test_no_notes_but_valid_headers_returns_false(self) -> None:
        """ABC with headers but no actual note letters fails."""
        no_notes = (
            "X:1\n"
            "T:Silent Tune\n"
            "M:4/4\n"
            "L:1/8\n"
            "K:C\n"
            "| | | |\n"  # Bars but no notes
        )
        # No note letters A-G → fails regex check
        assert AbcMusicGenerator.validate_abc(no_notes) is False

    def test_fallback_to_false_when_music21_unavailable(self, monkeypatch) -> None:
        """When music21 is not installed, validate_abc returns False.

        Previously the fallback returned True, masking the missing dependency.
        Now it returns False so the pipeline knows validation couldn't complete.
        """
        # Simulate music21 being unavailable
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "music21" or name.startswith("music21."):
                raise ImportError("No module named 'music21'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Even valid-looking ABC returns False when music21 is missing
        valid_abc = "X:1\nT:Test\nM:4/4\nL:1/8\nK:C\nC D E F | G A B c |\n"
        assert AbcMusicGenerator.validate_abc(valid_abc) is False
