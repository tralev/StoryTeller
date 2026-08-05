import struct
from dataclasses import replace

import pytest

from src.narrative.media import (FULL_SIZE, THUMB_SIZE, derive_thumbnail, deterministic_image,
                                 generate_score, score_to_midi, validate_midi, validate_png,
                                 validate_score)


def test_full_png_and_derived_thumbnail_decode_at_exact_sizes():
    full = deterministic_image(42)
    validate_png(full, FULL_SIZE)
    thumb = derive_thumbnail(full)
    validate_png(thumb, THUMB_SIZE)
    with pytest.raises(ValueError): validate_png(b"corrupt", FULL_SIZE)
    with pytest.raises(ValueError, match="PNG-SIZE"): validate_png(thumb, FULL_SIZE)


def test_structured_score_and_type1_960ppq_midi():
    score = generate_score(42, 84); validate_score(score)
    result = validate_midi(score_to_midi(score), score)
    assert result["format"] == 1 and result["ppq"] == 960 and result["duration_ticks"] > 0


def test_wrong_midi_type_ppq_empty_and_sysex_are_rejected():
    score = generate_score(42, 84)
    midi = bytearray(score_to_midi(score))
    midi[8:10] = struct.pack(">H", 0)
    with pytest.raises(ValueError, match="MIDI-FORMAT"): validate_midi(bytes(midi), score)
    midi = bytearray(score_to_midi(score)); midi[12:14] = struct.pack(">H", 480)
    with pytest.raises(ValueError, match="MIDI-FORMAT"): validate_midi(bytes(midi), score)
    with pytest.raises(ValueError): validate_midi(b"MThd", score)


def test_invalid_score_program_loop_and_score_midi_mismatch_are_rejected():
    score = generate_score(42, 84)
    with pytest.raises(ValueError, match="SCORE-PROGRAM"):
        validate_score(replace(score, program=120))
    with pytest.raises(ValueError, match="SCORE-LOOP"):
        validate_score(replace(score, loop_end_tick=0))
    midi = score_to_midi(score)
    with pytest.raises(ValueError, match="MIDI-SCORE-MISMATCH"):
        validate_midi(midi, replace(score, loop_end_tick=score.loop_end_tick + 960))
    forbidden = midi.replace(b"\x00\xc0\x30", b"\x00\xc0\x78", 1)
    with pytest.raises(ValueError, match="MIDI-PROGRAM"):
        validate_midi(forbidden)
    no_marker = midi.replace(b"LOOP_START", b"NOOP_START", 1)
    with pytest.raises(ValueError, match="MIDI-LOOP"):
        validate_midi(no_marker)
