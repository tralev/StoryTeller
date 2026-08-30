"""Atomic deterministic PNG/thumbnail/score/MIDI production and verification."""

from __future__ import annotations

import hashlib
import struct
import zlib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..storage.fs import atomic_write_bytes
from ..worldgen.numeric import SplitMix64, identity, stable_id
from .models import (
    SCORE_EVENT_KINDS,
    SCORE_MARKER_NAMES,
    SCORE_PPQ,
    SCORE_SCHEMA_VERSION,
    Beat,
    MediaRef,
    ScoreEvent,
    ScoreTrack,
    StructuredScore,
)

FULL_SIZE = (1024, 1024)
THUMB_SIZE = (256, 256)
ALLOWED_PROGRAMS = frozenset(range(0, 96))
_CONTROL_CHANGE_NUMBER = 11  # Expression — the fixed CC every "control" event writes.
_PITCH_BEND_RANGE_SEMITONES = 2  # Declared via RPN 0,0 once per pitch-bend-capable track.
_DRUM_CHANNEL = 9  # 0-indexed MIDI channel 10, the GM percussion channel.


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


SRGB_RENDERING_INTENT_PERCEPTUAL = 0


def encode_png(width: int, height: int, pixels: bytes) -> bytes:
    """Encode noninterlaced 8-bit RGBA pixels with an explicit sRGB chunk.

    ``pixels`` is packed RGBA (4 bytes/pixel), matching package-v2.md's
    fixed PNG policy: "All PNGs: non-interlaced, 8-bit RGBA, sRGB,
    non-animated."
    """
    if len(pixels) != width * height * 4:
        raise ValueError("PNG-PIXELS: wrong pixel count")
    rows = b"".join(b"\0" + pixels[y * width * 4 : (y + 1) * width * 4] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"sRGB", struct.pack(">B", SRGB_RENDERING_INTENT_PERCEPTUAL))
        + _chunk(b"IDAT", zlib.compress(rows, 9))
        + _chunk(b"IEND", b"")
    )


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Decode a noninterlaced 8-bit RGBA PNG, returning packed RGBA pixels."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG-SIGNATURE: corrupt PNG")
    offset, width, height, compressed, has_srgb = 8, 0, 0, bytearray(), False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG-TRUNCATED: incomplete chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError("PNG-CRC: corrupt chunk")
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise ValueError("PNG-FORMAT: only noninterlaced RGBA8 is accepted")
        elif kind == b"sRGB":
            if len(payload) != 1:
                raise ValueError("PNG-SRGB: malformed sRGB chunk")
            has_srgb = True
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if not has_srgb:
        raise ValueError("PNG-SRGB: sRGB chunk is required")
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ValueError("PNG-DEFLATE: corrupt image data") from error
    stride = width * 4
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG-LENGTH: wrong decoded length")
    rows = []
    for y in range(height):
        row = raw[y * (stride + 1) : (y + 1) * (stride + 1)]
        if not row or row[0] != 0:
            raise ValueError("PNG-FILTER: unsupported authoritative filter")
        rows.append(row[1:])
    return width, height, b"".join(rows)


def validate_png(data: bytes, expected: tuple[int, int]) -> bytes:
    width, height, pixels = decode_png(data)
    if (width, height) != expected:
        raise ValueError(f"PNG-SIZE: expected {expected}, got {(width, height)}")
    return pixels


def deterministic_image(seed: int, width: int = FULL_SIZE[0], height: int = FULL_SIZE[1]) -> bytes:
    rng = SplitMix64(seed)
    base = (40 + rng.below(80), 30 + rng.below(60), 45 + rng.below(90))
    pixels = bytearray()
    for y in range(height):
        shade = y * 45 // max(1, height - 1)
        row_color = bytes(
            (
                min(255, base[0] + shade),
                min(255, base[1] + shade // 2),
                min(255, base[2] + shade),
                255,
            )
        )
        pixels.extend(row_color * width)
    return encode_png(width, height, bytes(pixels))


def derive_thumbnail(full_png: bytes) -> bytes:
    width, height, pixels = decode_png(full_png)
    tw, th = THUMB_SIZE
    thumb = bytearray()
    for y in range(th):
        sy = y * height // th
        for x in range(tw):
            sx = x * width // tw
            offset = (sy * width + sx) * 4
            thumb.extend(pixels[offset : offset + 4])
    return encode_png(tw, th, bytes(thumb))


def _event_sort_key(event: ScoreEvent) -> tuple[int, int, tuple[int, ...], str]:
    """ "Ordered by start tick, event kind, pitch tuple, then event ID" (api.md)."""
    return (event.start.tick, SCORE_EVENT_KINDS.index(event.kind), event.pitches, event.event_id)


def _beat_at(tick: int) -> Beat:
    return Beat.from_tick(tick)


def generate_score(
    seed: int,
    tempo_bpm: int,
    node_id: str,
    source_ids: tuple[str, ...],
    producer_fingerprint: str,
) -> StructuredScore:
    """Deterministic placeholder composition: melody, bass, and percussion tracks.

    Not an LLM/music21 composition (see src/backends/midi_backend.py for that,
    currently unwired from the production pipeline) — a fixed, seeded shape
    that already satisfies the full api.md StructuredScore contract, including
    a real intro/loop/outro structure and all four markers.
    """
    rng = SplitMix64(seed)
    intro_end = _beat_at(SCORE_PPQ)
    loop_start = intro_end
    loop_length = 8 * SCORE_PPQ
    loop_end = _beat_at(loop_start.tick + loop_length)
    outro_start = loop_end
    duration = _beat_at(outro_start.tick + SCORE_PPQ)

    def score_event_id(track: str, index: int) -> str:
        return stable_id(
            "scoreevent",
            seed,
            identity("node_id", node_id),
            identity("track", track),
            identity("index", index),
        )

    melody = [
        ScoreEvent(
            score_event_id("melody", 0),
            "note",
            _beat_at(0),
            intro_end,
            (48 + rng.below(12),),
            50,
            None,
        )
    ]
    for index in range(8):
        melody.append(
            ScoreEvent(
                score_event_id("melody", index + 1),
                "note",
                _beat_at(loop_start.tick + index * SCORE_PPQ),
                _beat_at(720),
                (48 + rng.below(25),),
                70 + rng.below(30),
                None,
            )
        )
    melody.append(
        ScoreEvent(
            score_event_id("melody", 9),
            "note",
            outro_start,
            _beat_at(duration.tick - outro_start.tick),
            (48 + rng.below(12),),
            40,
            None,
        )
    )

    bass = tuple(
        ScoreEvent(
            score_event_id("bass", index),
            "note",
            _beat_at(loop_start.tick + index * SCORE_PPQ * 2),
            _beat_at(SCORE_PPQ * 2),
            (28 + rng.below(13),),
            60 + rng.below(20),
            None,
        )
        for index in range(loop_length // (SCORE_PPQ * 2))
    )
    percussion = tuple(
        ScoreEvent(
            score_event_id("percussion", index),
            "note",
            _beat_at(loop_start.tick + index * SCORE_PPQ // 2),
            _beat_at(SCORE_PPQ // 4),
            (36,),
            50 + rng.below(40),
            None,
        )
        for index in range(loop_length // (SCORE_PPQ // 2))
    )

    tracks = (
        ScoreTrack("melody", "melody", 48, False, tuple(sorted(melody, key=_event_sort_key))),
        ScoreTrack("bass", "bass", 32, False, tuple(sorted(bass, key=_event_sort_key))),
        ScoreTrack(
            "percussion", "percussion", None, True, tuple(sorted(percussion, key=_event_sort_key))
        ),
    )
    zero = {"numerator": 0, "denominator": 1}
    draft = StructuredScore(
        SCORE_SCHEMA_VERSION,
        node_id,
        SCORE_PPQ,
        duration,
        ({"beat": zero, "bpm": tempo_bpm},),
        ({"beat": zero, "numerator": 4, "denominator": 4},),
        ({"beat": zero, "sharps": 0, "minor": False},),
        tracks,
        {
            "INTRO_END": intro_end,
            "LOOP_START": loop_start,
            "LOOP_END": loop_end,
            "OUTRO_START": outro_start,
        },
        tuple(sorted(set(source_ids))),
        producer_fingerprint,
        "",
    )
    validate_score(draft)
    midi_bytes = score_to_smf_type1(draft)
    return replace(draft, expected_midi_sha256=hashlib.sha256(midi_bytes).hexdigest())


def _beat_from_mapping(value: object) -> Beat | None:
    if not isinstance(value, Mapping):
        return None
    numerator, denominator = value.get("numerator"), value.get("denominator")
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, int)
        or not isinstance(denominator, int)
    ):
        return None
    try:
        return Beat(numerator, denominator)
    except ValueError:
        return None


def _validate_event(event: ScoreEvent, duration_tick: int) -> None:
    if event.kind not in SCORE_EVENT_KINDS:
        raise ValueError("SCORE-EVENT-KIND: unknown event kind")
    if event.duration.tick <= 0:
        raise ValueError("SCORE-EVENT-DURATION: duration must be positive")
    if event.start.tick < 0 or event.start.tick + event.duration.tick > duration_tick:
        raise ValueError("SCORE-EVENT-RANGE: event exceeds score duration")
    if event.kind in ("note", "chord"):
        if not event.pitches or any(not 0 <= pitch <= 127 for pitch in event.pitches):
            raise ValueError("SCORE-EVENT-PITCH: invalid pitch set")
        if event.kind == "note" and len(event.pitches) != 1:
            raise ValueError("SCORE-EVENT-PITCH: a note carries exactly one pitch")
        if event.kind == "chord" and len(event.pitches) < 2:
            raise ValueError("SCORE-EVENT-PITCH: a chord carries at least two pitches")
        if event.velocity is None or not 1 <= event.velocity <= 127:
            raise ValueError("SCORE-EVENT-VELOCITY: invalid sounding velocity")
        if event.value is not None:
            raise ValueError("SCORE-EVENT-SHAPE: note/chord events carry no value")
    elif event.kind == "rest":
        if event.pitches or event.velocity is not None or event.value is not None:
            raise ValueError("SCORE-EVENT-SHAPE: rest events carry no pitch, velocity, or value")
    elif event.kind == "control":
        if event.pitches or event.velocity is not None:
            raise ValueError("SCORE-EVENT-SHAPE: control events carry no pitch or velocity")
        if event.value is None or not 0 <= event.value <= 127:
            raise ValueError("SCORE-EVENT-VALUE: control value must be 0..127")
    elif event.kind == "pitch_bend":
        if event.pitches or event.velocity is not None:
            raise ValueError("SCORE-EVENT-SHAPE: pitch_bend events carry no pitch or velocity")
        if event.value is None or not -8192 <= event.value <= 8191:
            raise ValueError("SCORE-EVENT-VALUE: pitch bend must be -8192..8191")


def validate_score(score: StructuredScore) -> None:
    if score.schema_version != SCORE_SCHEMA_VERSION or score.ppq != SCORE_PPQ:
        raise ValueError("SCORE-HEADER: unsupported score format")
    if not score.node_id:
        raise ValueError("SCORE-HEADER: node_id is required")
    if score.duration.tick <= 0:
        raise ValueError("SCORE-DURATION: duration must be positive")
    if score.source_ids != tuple(sorted(set(score.source_ids))):
        raise ValueError("SCORE-SOURCES: source_ids must be canonical")
    if set(score.markers) != set(SCORE_MARKER_NAMES):
        raise ValueError("SCORE-MARKERS: exactly the four frozen markers are required")
    intro_end = score.markers["INTRO_END"].tick
    loop_start = score.markers["LOOP_START"].tick
    loop_end = score.markers["LOOP_END"].tick
    outro_start = score.markers["OUTRO_START"].tick
    if not 0 <= intro_end <= loop_start < loop_end <= outro_start <= score.duration.tick:
        raise ValueError("SCORE-MARKERS: markers must be monotonic and within duration")
    if not score.tempo_map or not score.time_signature_map or not score.key_signature_map:
        raise ValueError("SCORE-MAPS: tempo/time/key maps must be non-empty")
    for entry in score.tempo_map:
        beat = _beat_from_mapping(entry.get("beat"))
        bpm = entry.get("bpm")
        if (
            beat is None
            or not 0 <= beat.tick <= score.duration.tick
            or isinstance(bpm, bool)
            or not isinstance(bpm, int)
            or not 20 <= bpm <= 300
        ):
            raise ValueError("SCORE-TEMPO: invalid tempo_map entry")
    for entry in score.time_signature_map:
        beat = _beat_from_mapping(entry.get("beat"))
        numerator, denominator = entry.get("numerator"), entry.get("denominator")
        if (
            beat is None
            or not 0 <= beat.tick <= score.duration.tick
            or isinstance(numerator, bool)
            or not isinstance(numerator, int)
            or not 1 <= numerator <= 32
            or denominator not in (1, 2, 4, 8, 16, 32)
        ):
            raise ValueError("SCORE-TIME-SIGNATURE: invalid time_signature_map entry")
    for entry in score.key_signature_map:
        beat = _beat_from_mapping(entry.get("beat"))
        sharps, minor = entry.get("sharps"), entry.get("minor")
        if (
            beat is None
            or not 0 <= beat.tick <= score.duration.tick
            or isinstance(sharps, bool)
            or not isinstance(sharps, int)
            or not -7 <= sharps <= 7
            or not isinstance(minor, bool)
        ):
            raise ValueError("SCORE-KEY-SIGNATURE: invalid key_signature_map entry")
    if not score.tracks:
        raise ValueError("SCORE-TRACKS: at least one track is required")
    track_ids = tuple(track.track_id for track in score.tracks)
    if len(set(track_ids)) != len(track_ids) or any(not tid for tid in track_ids):
        raise ValueError("SCORE-TRACKS: track IDs must be unique and non-empty")
    for track in score.tracks:
        if track.drum_channel:
            if track.gm_program is not None:
                raise ValueError("SCORE-PROGRAM: drum tracks carry no gm_program")
        elif track.gm_program is None or track.gm_program not in ALLOWED_PROGRAMS:
            raise ValueError("SCORE-PROGRAM: forbidden or missing MIDI program")
        if not track.events:
            raise ValueError("SCORE-EVENTS: track must have at least one event")
        if track.events != tuple(sorted(track.events, key=_event_sort_key)):
            raise ValueError("SCORE-EVENTS: events must be canonically ordered")
        event_ids = tuple(event.event_id for event in track.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("SCORE-EVENTS: event IDs must be unique within a track")
        for event in track.events:
            _validate_event(event, score.duration.tick)


def _vlq(value: int) -> bytes:
    result = bytearray([value & 0x7F])
    value >>= 7
    while value:
        result.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(result)


def _events_to_track_bytes(events: list[tuple[int, int, bytes]]) -> bytes:
    track = bytearray()
    previous = 0
    for tick, _, raw in sorted(events, key=lambda item: (item[0], item[1])):
        track.extend(_vlq(tick - previous))
        track.extend(raw)
        previous = tick
    track.extend(b"\x00\xff\x2f\x00")
    return bytes(track)


def _mapping_int(entry: Mapping[str, object], key: str) -> int:
    value = entry[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"SCORE-MAP-FIELD: {key} must be an integer")
    return value


def _mapping_tick(entry: Mapping[str, object]) -> int:
    beat = _beat_from_mapping(entry.get("beat"))
    if beat is None:
        raise ValueError("SCORE-MAP-FIELD: beat is required")
    return beat.tick


def _render_conductor_track(score: StructuredScore) -> bytes:
    events: list[tuple[int, int, bytes]] = []
    for entry in score.tempo_map:
        microseconds = 60_000_000 // _mapping_int(entry, "bpm")
        events.append((_mapping_tick(entry), 0, b"\xff\x51\x03" + microseconds.to_bytes(3, "big")))
    for entry in score.time_signature_map:
        numerator = _mapping_int(entry, "numerator")
        denominator = _mapping_int(entry, "denominator")
        power = denominator.bit_length() - 1
        events.append((_mapping_tick(entry), 0, bytes((0xFF, 0x58, 0x04, numerator, power, 24, 8))))
    for entry in score.key_signature_map:
        sharps = _mapping_int(entry, "sharps")
        minor = bool(entry["minor"])
        events.append(
            (
                _mapping_tick(entry),
                0,
                bytes((0xFF, 0x59, 0x02)) + struct.pack(">b", sharps) + bytes((1 if minor else 0,)),
            )
        )
    for name in SCORE_MARKER_NAMES:
        text = name.encode("ascii")
        events.append((score.markers[name].tick, 1, bytes((0xFF, 0x06, len(text))) + text))
    return _events_to_track_bytes(events)


def _channel_for(index: int, drum: bool) -> int:
    if drum:
        return _DRUM_CHANNEL
    channel = index if index < _DRUM_CHANNEL else index + 1
    if channel > 15:
        raise ValueError("SCORE-TRACKS: too many non-drum tracks for 16 MIDI channels")
    return channel


def _render_instrument_track(index: int, track: ScoreTrack) -> bytes:
    channel = _channel_for(index, track.drum_channel)
    events: list[tuple[int, int, bytes]] = []
    if track.gm_program is not None:
        events.append((0, 1, bytes((0xC0 | channel, track.gm_program))))
    if any(event.kind == "pitch_bend" for event in track.events):
        # Declare a fixed +/-2 semitone pitch-bend range via RPN 0,0 once.
        events.append((0, 1, bytes((0xB0 | channel, 0x65, 0x00))))
        events.append((0, 1, bytes((0xB0 | channel, 0x64, 0x00))))
        events.append((0, 1, bytes((0xB0 | channel, 0x06, _PITCH_BEND_RANGE_SEMITONES))))
        events.append((0, 1, bytes((0xB0 | channel, 0x26, 0x00))))
    for event in track.events:
        start, end = event.start.tick, event.start.tick + event.duration.tick
        if event.kind in ("note", "chord"):
            for pitch in event.pitches:
                assert event.velocity is not None
                events.append((start, 3, bytes((0x90 | channel, pitch, event.velocity))))
                events.append((end, 0, bytes((0x80 | channel, pitch, 0))))
        elif event.kind == "control":
            assert event.value is not None
            events.append((start, 1, bytes((0xB0 | channel, _CONTROL_CHANGE_NUMBER, event.value))))
        elif event.kind == "pitch_bend":
            assert event.value is not None
            value = event.value + 8192
            events.append((start, 2, bytes((0xE0 | channel, value & 0x7F, (value >> 7) & 0x7F))))
        # "rest" events carry no MIDI bytes.
    return _events_to_track_bytes(events)


def score_to_smf_type1(score: StructuredScore) -> bytes:
    """Render deterministic SMF Type 1 bytes. Ignores expected_midi_sha256 by design
    (api.md: "The score is first rendered without consulting expected_midi_sha256")."""
    validate_score(score)
    conductor = _render_conductor_track(score)
    instrument_tracks = [
        _render_instrument_track(index, track) for index, track in enumerate(score.tracks)
    ]
    track_count = 1 + len(instrument_tracks)
    body = b"".join(
        b"MTrk" + struct.pack(">I", len(track)) + track for track in (conductor, *instrument_tracks)
    )
    return b"MThd" + struct.pack(">IHHH", 6, 1, track_count, SCORE_PPQ) + body


def _read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("MIDI-TRUNCATED: VLQ")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise ValueError("MIDI-VLQ: too long")


def validate_midi(data: bytes, score: StructuredScore | None = None) -> dict[str, int]:
    if len(data) < 14 or data[:4] != b"MThd" or struct.unpack(">I", data[4:8])[0] != 6:
        raise ValueError("MIDI-HEADER: corrupt SMF")
    fmt, tracks, ppq = struct.unpack(">HHH", data[8:14])
    if fmt != 1 or tracks < 2 or ppq != SCORE_PPQ:
        raise ValueError("MIDI-FORMAT: requires SMF Type 1 and 960 PPQ")
    offset, note_events, max_tick, markers = 14, 0, 0, set()
    for _ in range(tracks):
        if data[offset : offset + 4] != b"MTrk":
            raise ValueError("MIDI-TRACK: missing track")
        length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        track, offset = data[offset + 8 : offset + 8 + length], offset + 8 + length
        cursor = tick = 0
        while cursor < len(track):
            delta, cursor = _read_vlq(track, cursor)
            tick += delta
            max_tick = max(max_tick, tick)
            status = track[cursor]
            cursor += 1
            if status in (0xF0, 0xF7):
                raise ValueError("MIDI-SYSEX: forbidden SysEx")
            if status == 0xFF:
                kind = track[cursor]
                cursor += 1
                size, cursor = _read_vlq(track, cursor)
                payload = track[cursor : cursor + size]
                cursor += size
                if kind == 0x06:
                    markers.add(payload.decode("ascii", "ignore"))
            elif status & 0xF0 in (0x80, 0x90):
                if cursor + 2 > len(track):
                    raise ValueError("MIDI-EVENT: truncated note")
                if not 0 <= track[cursor] <= 127 or not 0 <= track[cursor + 1] <= 127:
                    raise ValueError("MIDI-EVENT: data byte out of range")
                note_events += 1
                cursor += 2
            elif status & 0xF0 == 0xB0:
                if cursor + 2 > len(track):
                    raise ValueError("MIDI-EVENT: truncated control change")
                cursor += 2
            elif status & 0xF0 == 0xE0:
                if cursor + 2 > len(track):
                    raise ValueError("MIDI-EVENT: truncated pitch bend")
                cursor += 2
            elif status & 0xF0 == 0xC0:
                if cursor >= len(track) or track[cursor] not in ALLOWED_PROGRAMS:
                    raise ValueError("MIDI-PROGRAM: forbidden program")
                cursor += 1
            else:
                raise ValueError("MIDI-EVENT: unsupported event")
    if offset != len(data) or note_events == 0 or max_tick <= 0:
        raise ValueError("MIDI-DURATION: empty or zero-duration MIDI")
    if markers != set(SCORE_MARKER_NAMES):
        raise ValueError("MIDI-LOOP: missing or invalid loop/intro/outro markers")
    if score is not None:
        if max_tick != score.duration.tick:
            raise ValueError("MIDI-SCORE-MISMATCH: duration differs from score")
        if hashlib.sha256(data).hexdigest() != score.expected_midi_sha256:
            raise ValueError("MIDI-SCORE-MISMATCH: MIDI hash differs from score")
    return {
        "format": fmt,
        "tracks": tracks,
        "ppq": ppq,
        "events": note_events,
        "duration_ticks": max_tick,
    }


def publish_verified(
    path: Path,
    data: bytes,
    validator: Any,
    *,
    seed: int,
    fingerprint: str,
    dependencies: tuple[str, ...],
) -> MediaRef:
    validator(data)
    atomic_write_bytes(path, data)
    published = path.read_bytes()
    validator(published)
    digest = hashlib.sha256(published).hexdigest()
    return MediaRef(str(path), digest, seed, fingerprint, tuple(sorted(dependencies)))


def verify_ref(ref: MediaRef) -> bool:
    path = Path(ref.path)
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == ref.sha256
