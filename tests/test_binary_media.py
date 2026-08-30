import hashlib
import json
import struct
from dataclasses import replace

import pytest

from src.narrative.media import (
    FULL_SIZE,
    THUMB_SIZE,
    derive_thumbnail,
    deterministic_image,
    generate_score,
    score_to_smf_type1,
    validate_midi,
    validate_png,
    validate_score,
)
from src.narrative.models import Beat, ScoreEvent
from src.narrative.pipeline import _score_from_dict
from src.worldgen.artifacts import canonical_json

SOURCE_IDS = (
    "civilization_00000000000000000000000000000001",
    "event_00000000000000000000000000000001",
)


def _score(seed: int = 42, tempo_bpm: int = 84):
    return generate_score(
        seed, tempo_bpm, "node_00000000000000000000000000000001", SOURCE_IDS, "test.fixture.v1"
    )


def test_full_png_and_derived_thumbnail_decode_at_exact_sizes():
    full = deterministic_image(42)
    validate_png(full, FULL_SIZE)
    thumb = derive_thumbnail(full)
    validate_png(thumb, THUMB_SIZE)
    with pytest.raises(ValueError):
        validate_png(b"corrupt", FULL_SIZE)
    with pytest.raises(ValueError, match="PNG-SIZE"):
        validate_png(thumb, FULL_SIZE)


def test_structured_score_and_type1_960ppq_midi():
    score = _score()
    validate_score(score)
    result = validate_midi(score_to_smf_type1(score), score)
    assert result["format"] == 1 and result["ppq"] == 960 and result["duration_ticks"] > 0
    # One conductor track plus one per declared score track.
    assert result["tracks"] == 1 + len(score.tracks)


def test_score_has_full_intro_loop_outro_marker_structure():
    score = _score()
    assert set(score.markers) == {"INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START"}
    assert (
        0
        <= score.markers["INTRO_END"].tick
        <= score.markers["LOOP_START"].tick
        < score.markers["LOOP_END"].tick
        <= score.markers["OUTRO_START"].tick
        <= score.duration.tick
    )
    assert score.expected_midi_sha256
    roles = {track.role for track in score.tracks}
    assert {"melody", "bass", "percussion"} <= roles
    drum_tracks = [track for track in score.tracks if track.drum_channel]
    assert drum_tracks and all(track.gm_program is None for track in drum_tracks)


def test_score_json_round_trips_through_canonical_json():
    score = _score()
    restored = _score_from_dict(json.loads(canonical_json(score)))
    assert restored == score
    validate_score(restored)


def test_wrong_midi_type_ppq_empty_and_sysex_are_rejected():
    score = _score()
    midi = bytearray(score_to_smf_type1(score))
    midi[8:10] = struct.pack(">H", 0)
    with pytest.raises(ValueError, match="MIDI-FORMAT"):
        validate_midi(bytes(midi), score)
    midi = bytearray(score_to_smf_type1(score))
    midi[12:14] = struct.pack(">H", 480)
    with pytest.raises(ValueError, match="MIDI-FORMAT"):
        validate_midi(bytes(midi), score)
    with pytest.raises(ValueError):
        validate_midi(b"MThd", score)


def test_invalid_markers_and_score_midi_mismatch_are_rejected():
    score = _score()
    with pytest.raises(ValueError, match="SCORE-MARKERS"):
        validate_score(
            replace(
                score,
                markers={
                    **score.markers,
                    "LOOP_END": score.markers["LOOP_START"],
                },
            )
        )
    midi = score_to_smf_type1(score)
    with pytest.raises(ValueError, match="MIDI-SCORE-MISMATCH"):
        validate_midi(midi, replace(score, expected_midi_sha256="0" * 64))
    forbidden = midi.replace(b"\x00\xc0\x30", b"\x00\xc0\x78", 1)
    with pytest.raises(ValueError, match="MIDI-PROGRAM"):
        validate_midi(forbidden)
    no_marker = midi.replace(b"LOOP_START", b"NOOP_START", 1)
    with pytest.raises(ValueError, match="MIDI-LOOP"):
        validate_midi(no_marker)


def test_forbidden_or_missing_track_program_is_rejected():
    score = _score()
    melody = next(track for track in score.tracks if track.track_id == "melody")
    forbidden = replace(melody, gm_program=120)
    with pytest.raises(ValueError, match="SCORE-PROGRAM"):
        validate_score(replace(score, tracks=(forbidden,) + score.tracks[1:]))
    percussion = next(track for track in score.tracks if track.drum_channel)
    carries_program = replace(percussion, gm_program=0)
    tracks = tuple(
        carries_program if t.track_id == percussion.track_id else t for t in score.tracks
    )
    with pytest.raises(ValueError, match="SCORE-PROGRAM"):
        validate_score(replace(score, tracks=tracks))


def test_events_must_be_canonically_ordered():
    score = _score()
    melody = next(track for track in score.tracks if track.track_id == "melody")
    reversed_events = tuple(reversed(melody.events))
    shuffled = replace(melody, events=reversed_events)
    with pytest.raises(ValueError, match="SCORE-EVENTS"):
        validate_score(replace(score, tracks=(shuffled,) + score.tracks[1:]))


def test_control_and_pitch_bend_events_validate_and_render():
    score = _score()
    melody = next(track for track in score.tracks if track.track_id == "melody")
    extra = (
        ScoreEvent("control_00", "control", Beat(0, 1), Beat(1, 8), (), None, 64),
        ScoreEvent("bend_00", "pitch_bend", Beat(0, 1), Beat(1, 8), (), None, 0),
    )
    events = tuple(
        sorted(
            melody.events + extra,
            key=lambda e: (
                e.start.tick,
                ["chord", "control", "note", "pitch_bend", "rest"].index(e.kind),
                e.pitches,
                e.event_id,
            ),
        )
    )
    updated_track = replace(melody, events=events)
    updated = replace(score, tracks=(updated_track,) + score.tracks[1:])
    validate_score(updated)
    midi = score_to_smf_type1(updated)
    rehashed = replace(updated, expected_midi_sha256=hashlib.sha256(midi).hexdigest())
    result = validate_midi(midi, rehashed)
    assert result["duration_ticks"] == updated.duration.tick


def test_beat_rejects_non_reduced_zero_denominator_and_inexact_ticks():
    Beat(1, 4)  # sanity: a valid reduced beat exactly divides 960
    with pytest.raises(ValueError, match="BEAT-REDUCED"):
        Beat(2, 4)
    with pytest.raises(ValueError, match="BEAT-DENOMINATOR"):
        Beat(1, 0)
    with pytest.raises(ValueError, match="BEAT-TICK"):
        Beat(1, 7)


def test_score_track_requires_distinct_nonempty_track_ids():
    score = _score()
    duplicated = replace(score.tracks[1], track_id=score.tracks[0].track_id)
    with pytest.raises(ValueError, match="SCORE-TRACKS"):
        validate_score(replace(score, tracks=(score.tracks[0], duplicated, score.tracks[2])))


def test_note_event_shape_rules_are_enforced():
    score = _score()
    melody = next(track for track in score.tracks if track.track_id == "melody")
    bad_note = replace(melody.events[0], pitches=(60, 64))  # "note" must carry exactly one pitch
    with pytest.raises(ValueError, match="SCORE-EVENT-PITCH"):
        _validate_single_event(score, melody, bad_note)


def _validate_single_event(score, track, event) -> None:
    events = (event,) + track.events[1:]
    updated_track = replace(track, events=events)
    validate_score(replace(score, tracks=(updated_track,) + score.tracks[1:]))
