"""Atomic deterministic PNG/thumbnail/score/MIDI production and verification."""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..storage.fs import atomic_write_bytes
from ..worldgen.artifacts import canonical_json
from ..worldgen.numeric import SplitMix64
from .models import MediaRef, ScoreNote, StructuredScore

FULL_SIZE = (1024, 1024)
THUMB_SIZE = (256, 256)
ALLOWED_PROGRAMS = frozenset(range(0, 96))


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height * 3:
        raise ValueError("PNG-PIXELS: wrong pixel count")
    rows = b"".join(b"\0" + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) \
        + _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b"")


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG-SIGNATURE: corrupt PNG")
    offset, width, height, compressed = 8, 0, 0, bytearray()
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG-TRUNCATED: incomplete chunk")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError("PNG-CRC: corrupt chunk")
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0):
                raise ValueError("PNG-FORMAT: only noninterlaced RGB8 is accepted")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ValueError("PNG-DEFLATE: corrupt image data") from error
    stride = width * 3
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG-LENGTH: wrong decoded length")
    rows = []
    for y in range(height):
        row = raw[y * (stride + 1):(y + 1) * (stride + 1)]
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
        row_color = bytes((min(255, base[0] + shade), min(255, base[1] + shade // 2),
                           min(255, base[2] + shade)))
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
            offset = (sy * width + sx) * 3
            thumb.extend(pixels[offset:offset + 3])
    return encode_png(tw, th, bytes(thumb))


def generate_score(seed: int, tempo_bpm: int) -> StructuredScore:
    rng = SplitMix64(seed)
    notes = tuple(ScoreNote(index * 960, 720, 48 + rng.below(25), 70 + rng.below(30))
                  for index in range(8))
    return StructuredScore(1, 960, tempo_bpm, 0, 8 * 960, 48, notes)


def validate_score(score: StructuredScore) -> None:
    if score.format_version != 1 or score.ppq != 960 or not 20 <= score.tempo_bpm <= 300:
        raise ValueError("SCORE-HEADER: unsupported score format")
    if score.program not in ALLOWED_PROGRAMS:
        raise ValueError("SCORE-PROGRAM: forbidden MIDI program")
    if score.loop_start_tick != 0 or score.loop_end_tick <= score.loop_start_tick:
        raise ValueError("SCORE-LOOP: invalid loop markers")
    if not score.notes or any(note.duration_ticks <= 0 or not 0 <= note.pitch <= 127
                              or not 1 <= note.velocity <= 127 for note in score.notes):
        raise ValueError("SCORE-NOTES: invalid or empty note sequence")
    if max(note.start_tick + note.duration_ticks for note in score.notes) > score.loop_end_tick:
        raise ValueError("SCORE-LOOP: notes exceed loop end")


def _vlq(value: int) -> bytes:
    result = bytearray([value & 0x7F]); value >>= 7
    while value:
        result.insert(0, 0x80 | (value & 0x7F)); value >>= 7
    return bytes(result)


def score_to_midi(score: StructuredScore) -> bytes:
    validate_score(score)
    tempo = 60_000_000 // score.tempo_bpm
    conductor = b"\x00\xff\x51\x03" + tempo.to_bytes(3, "big") \
        + b"\x00\xff\x06\x0aLOOP_START" + _vlq(score.loop_end_tick) + b"\xff\x06\x08LOOP_END" \
        + b"\x00\xff\x2f\x00"
    events: list[tuple[int, int, bytes]] = [(0, 0, bytes((0xC0, score.program)))]
    for note in score.notes:
        events.append((note.start_tick, 2, bytes((0x90, note.pitch, note.velocity))))
        events.append((note.start_tick + note.duration_ticks, 1, bytes((0x80, note.pitch, 0))))
    track = bytearray(); previous = 0
    for tick, _, event in sorted(events, key=lambda item: (item[0], item[1], item[2])):
        track.extend(_vlq(tick - previous)); track.extend(event); previous = tick
    track.extend(b"\x00\xff\x2f\x00")
    return b"MThd" + struct.pack(">IHHH", 6, 1, 2, 960) \
        + b"MTrk" + struct.pack(">I", len(conductor)) + conductor \
        + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def _read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data): raise ValueError("MIDI-TRUNCATED: VLQ")
        byte = data[offset]; offset += 1; value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80: return value, offset
    raise ValueError("MIDI-VLQ: too long")


def validate_midi(data: bytes, score: StructuredScore | None = None) -> dict[str, int]:
    if len(data) < 14 or data[:4] != b"MThd" or struct.unpack(">I", data[4:8])[0] != 6:
        raise ValueError("MIDI-HEADER: corrupt SMF")
    fmt, tracks, ppq = struct.unpack(">HHH", data[8:14])
    if fmt != 1 or tracks < 2 or ppq != 960:
        raise ValueError("MIDI-FORMAT: requires SMF Type 1 and 960 PPQ")
    offset, note_events, max_tick, markers = 14, 0, 0, set()
    for _ in range(tracks):
        if data[offset:offset + 4] != b"MTrk": raise ValueError("MIDI-TRACK: missing track")
        length = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        track, offset = data[offset + 8:offset + 8 + length], offset + 8 + length
        cursor = tick = 0
        while cursor < len(track):
            delta, cursor = _read_vlq(track, cursor); tick += delta; max_tick = max(max_tick, tick)
            status = track[cursor]; cursor += 1
            if status in (0xF0, 0xF7): raise ValueError("MIDI-SYSEX: forbidden SysEx")
            if status == 0xFF:
                kind = track[cursor]; cursor += 1
                size, cursor = _read_vlq(track, cursor); payload = track[cursor:cursor + size]; cursor += size
                if kind == 0x06: markers.add(payload.decode("ascii", "ignore"))
            elif status & 0xF0 in (0x80, 0x90):
                if cursor + 2 > len(track): raise ValueError("MIDI-EVENT: truncated note")
                note_events += 1; cursor += 2
            elif status & 0xF0 == 0xC0:
                if cursor >= len(track) or track[cursor] not in ALLOWED_PROGRAMS:
                    raise ValueError("MIDI-PROGRAM: forbidden program")
                cursor += 1
            else:
                raise ValueError("MIDI-EVENT: unsupported event")
    if offset != len(data) or note_events == 0 or max_tick <= 0:
        raise ValueError("MIDI-DURATION: empty or zero-duration MIDI")
    if markers != {"LOOP_START", "LOOP_END"}:
        raise ValueError("MIDI-LOOP: missing or invalid loop markers")
    if score is not None and max_tick != score.loop_end_tick:
        raise ValueError("MIDI-SCORE-MISMATCH: duration differs from score")
    return {"format": fmt, "tracks": tracks, "ppq": ppq, "events": note_events, "duration_ticks": max_tick}


def publish_verified(path: Path, data: bytes, validator: Any, *, seed: int,
                     fingerprint: str, dependencies: tuple[str, ...]) -> MediaRef:
    validator(data)
    atomic_write_bytes(path, data)
    published = path.read_bytes(); validator(published)
    digest = hashlib.sha256(published).hexdigest()
    return MediaRef(str(path), digest, seed, fingerprint, tuple(sorted(dependencies)))


def verify_ref(ref: MediaRef) -> bool:
    path = Path(ref.path)
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == ref.sha256
