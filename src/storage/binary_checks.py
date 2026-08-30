"""Binary asset validation for .story packages (Phase 5.6R).

A packaged file path is not evidence of usability — the bytes must decode.
This module provides pure-stdlib PNG and MIDI validators (no Pillow /
music21 dependency, keeping the acceptance gate light):

  - ``validate_png``: signature, chunk structure, per-chunk CRC, bounded
    IDAT decompression, scanline validation, IHDR-first + IEND-last ordering,
    and positive dimensions.
  - ``validate_midi``: MThd header, MTrk chunks, delta-time parsing,
    rejects empty tracks and zero-duration files.

It also provides deterministic ``make_png`` / ``make_midi`` builders used
by tests and the fixture generator so every synthetic asset is genuinely
valid.

Usage:
    from .binary_checks import validate_png, validate_midi

    png = validate_png(png_bytes)
    if not png.ok:
        raise ...

    midi = validate_midi(midi_bytes)
    if not midi.ok:
        raise ...
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Default tempo assumption for MIDI duration (500000 us/qn = 120 BPM).
_DEFAULT_US_PER_QUARTER = 500_000


# ── PNG ──────────────────────────────────────────────────────────────────


@dataclass
class PngCheck:
    """Result of validating a PNG byte stream."""

    ok: bool
    error: str = ""
    width: int = 0
    height: int = 0

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


def validate_png(data: bytes) -> PngCheck:
    """Validate a PNG byte stream.

    Checks, in order:
      1. Signature ``\\x89PNG\\r\\n\\x1a\\n``
      2. IHDR must be the first chunk and carry positive dimensions
      3. Every chunk must fit within the buffer (truncation detection)
      4. Every chunk's CRC32 must match its type + data
      5. IEND must terminate the stream with no trailing data
      6. IDAT must be a valid bounded zlib stream whose decoded scanlines
         match the declared dimensions
    """
    if not data.startswith(PNG_SIGNATURE):
        return PngCheck(False, "Invalid PNG signature")
    if len(data) < 8 + 25:
        return PngCheck(False, "PNG too short to contain an IHDR chunk")

    pos = 8
    first = True
    seen_iend = False
    width = height = 0
    bit_depth = color_type = interlace = -1
    idat_parts: list[bytes] = []
    seen_idat = False
    idat_finished = False
    try:
        while pos < len(data):
            if pos + 8 > len(data):
                return PngCheck(False, "Truncated chunk header")
            (chunk_len,) = struct.unpack(">I", data[pos : pos + 4])
            chunk_type = data[pos + 4 : pos + 8]
            end = pos + 8 + chunk_len
            if end + 4 > len(data):
                return PngCheck(
                    False,
                    f"Truncated {chunk_type.decode('latin1', 'replace')!r} chunk",
                )
            chunk_data = data[pos + 8 : end]
            (crc,) = struct.unpack(">I", data[end : end + 4])
            if (zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF) != crc:
                return PngCheck(
                    False,
                    f"CRC mismatch in {chunk_type.decode('latin1', 'replace')!r} chunk",
                )
            if first:
                if chunk_type != b"IHDR":
                    return PngCheck(False, "IHDR chunk must be first")
                if chunk_len != 13:
                    return PngCheck(False, "IHDR chunk must be 13 bytes")
                width, height = struct.unpack(">II", chunk_data[0:8])
                bit_depth, color_type, compression, filtering, interlace = chunk_data[8:13]
                if width == 0 or height == 0:
                    return PngCheck(False, "Zero image dimensions")
                if compression != 0 or filtering != 0 or interlace not in (0, 1):
                    return PngCheck(False, "Unsupported PNG encoding method")
                first = False
            if chunk_type == b"IDAT":
                if idat_finished:
                    return PngCheck(False, "IDAT chunks must be consecutive")
                seen_idat = True
                idat_parts.append(chunk_data)
            elif seen_idat and chunk_type != b"IEND":
                idat_finished = True
            if chunk_type == b"IEND":
                seen_iend = True
                if end + 4 != len(data):
                    return PngCheck(False, "Unexpected data after IEND chunk")
                break
            pos = end + 4
    except (struct.error, ValueError):
        return PngCheck(False, "Malformed PNG structure")

    if not seen_iend:
        return PngCheck(False, "Missing IEND chunk")
    if not idat_parts:
        return PngCheck(False, "Missing IDAT image data")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if channels is None or bit_depth not in valid_depths[color_type]:
        return PngCheck(False, "Invalid PNG bit-depth/color-type combination")
    if interlace != 0:
        return PngCheck(False, "Interlaced PNG is not supported by the media profile")

    row_bytes = (width * channels * bit_depth + 7) // 8
    expected_bytes = height * (row_bytes + 1)
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(b"".join(idat_parts), expected_bytes + 1)
        if inflater.unconsumed_tail:
            return PngCheck(False, "IDAT data exceeds declared image dimensions")
        decoded += inflater.flush(max(1, expected_bytes + 1 - len(decoded)))
    except zlib.error as e:
        return PngCheck(False, f"Invalid IDAT zlib stream: {e}")
    if len(decoded) != expected_bytes or not inflater.eof or inflater.unused_data:
        return PngCheck(False, "IDAT data does not decode to the declared image dimensions")
    for row in range(height):
        if decoded[row * (row_bytes + 1)] > 4:
            return PngCheck(False, "Invalid PNG row filter")
    return PngCheck(True, width=width, height=height)


def make_png(
    width: int = 512,
    height: int = 512,
    rgb: tuple[int, int, int] = (128, 128, 128),
) -> bytes:
    """Build a minimal, structurally valid solid-color PNG with correct CRCs.

    Used by tests and the fixture generator so synthetic assets satisfy
    ``validate_png`` (including the dimension checks).
    """

    def _chunk(ctype: bytes, cdata: bytes) -> bytes:
        return (
            struct.pack(">I", len(cdata))
            + ctype
            + cdata
            + struct.pack(">I", zlib.crc32(ctype + cdata) & 0xFFFFFFFF)
        )

    # 8-bit RGB, no interlace
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width  # filter byte 0 + pixels
    idat = zlib.compress(row * height, level=9)
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


# ── MIDI ─────────────────────────────────────────────────────────────────


@dataclass
class MidiCheck:
    """Result of validating a Standard MIDI File byte stream."""

    ok: bool
    error: str = ""
    duration_s: float = 0.0
    tracks: int = 0
    format: int = 0
    division: int = 0


def _read_vlq(data: bytes, i: int) -> tuple[int, int]:
    """Read a variable-length quantity starting at ``i``.

    Returns (value, next_index). ``next_index`` may exceed len(data) for
    a truncated VLQ — callers check bounds.
    """
    value = 0
    count = 0
    while i < len(data):
        b = data[i]
        i += 1
        count += 1
        if count > 4:
            raise ValueError("MIDI VLQ exceeds four bytes")
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            return value, i
    raise ValueError("Truncated MIDI VLQ")


def _parse_track(body: bytes) -> tuple[int, int, int]:
    """Parse one MTrk body.

    Returns (total_delta_ticks, event_count). Tolerant of running status;
    stops at the end-of-track meta event (``FF 2F``). Raises on
    out-of-bounds access so callers can classify malformed tracks.
    """
    total_ticks = 0
    event_count = 0
    sounding_events = 0
    running_status: int | None = None
    saw_end = False
    i = 0
    while i < len(body):
        delta, i = _read_vlq(body, i)
        total_ticks += delta
        if i >= len(body):
            raise ValueError("Track ends after delta time")
        first = body[i]
        if first == 0xFF:  # meta event
            running_status = None
            if i + 2 > len(body):
                raise ValueError("Truncated meta event")
            mtype = body[i + 1]
            mlen, payload = _read_vlq(body, i + 2)
            end = payload + mlen
            if end > len(body):
                raise ValueError("Truncated meta-event payload")
            i = end
            if mtype == 0x2F:
                if mlen != 0 or i != len(body):
                    raise ValueError("End-of-track must be empty and final")
                saw_end = True
                break
            event_count += 1
            continue
        if first in (0xF0, 0xF7):
            running_status = None
            slen, payload = _read_vlq(body, i + 1)
            i = payload + slen
            if i > len(body):
                raise ValueError("Truncated SysEx payload")
            event_count += 1
            continue

        if first & 0x80:
            status = first
            i += 1
            if status >= 0xF0:
                raise ValueError("Unsupported system MIDI event")
            running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise ValueError("Running-status data without a status byte")

        top = status >> 4
        data_len = 1 if top in (0xC, 0xD) else 2
        if i + data_len > len(body):
            raise ValueError("Truncated channel MIDI event")
        event_data = body[i : i + data_len]
        if any(value & 0x80 for value in event_data):
            raise ValueError("Channel event data byte has status bit set")
        i += data_len
        event_count += 1
        if top == 0x9 and event_data[1] > 0:
            sounding_events += 1

    if not saw_end:
        raise ValueError("Missing end-of-track event")
    return total_ticks, event_count, sounding_events


def validate_midi(data: bytes) -> MidiCheck:
    """Validate a Standard MIDI File.

    Checks:
      1. ``MThd`` header with length 6 and a non-zero division
      2. At least one ``MTrk`` chunk, each fully within the buffer
      3. No empty tracks (tracks must contain at least one event)
      4. File duration (delta-time sum x default tempo) must be > 0

    Duration uses the default 120 BPM tempo when no tempo meta events are
    parsed — the goal is to reject silent/empty files, not to be a
    performance-accurate sequencer.
    """
    if len(data) < 14 or data[0:4] != b"MThd":
        return MidiCheck(False, "Invalid MIDI header (missing MThd)")
    (hdr_len,) = struct.unpack(">I", data[4:8])
    if hdr_len != 6:
        return MidiCheck(False, "Malformed MThd header")
    midi_format, declared_tracks, division = struct.unpack(">HHH", data[8:14])
    if midi_format not in (0, 1):
        return MidiCheck(False, f"Unsupported MIDI format {midi_format}")
    if declared_tracks == 0:
        return MidiCheck(False, "No MTrk chunks declared")
    if midi_format == 0 and declared_tracks != 1:
        return MidiCheck(False, "Invalid MIDI track count for format 0")
    if division == 0:
        return MidiCheck(False, "Zero division in MIDI header")
    smpte = bool(division & 0x8000)

    pos = 14
    track_count = 0
    max_ticks = 0
    sounding_events = 0
    try:
        while pos < len(data):
            if data[pos : pos + 4] != b"MTrk":
                return MidiCheck(False, "Corrupt MIDI chunk (expected MTrk)")
            (tlen,) = struct.unpack(">I", data[pos + 4 : pos + 8])
            if pos + 8 + tlen > len(data):
                return MidiCheck(False, "Truncated MTrk chunk")
            body = data[pos + 8 : pos + 8 + tlen]
            track_count += 1
            ticks, event_count, track_sounding = _parse_track(body)
            if event_count == 0:
                return MidiCheck(False, "Empty track (no events)")
            max_ticks = max(max_ticks, ticks)
            sounding_events += track_sounding
            pos += 8 + tlen
    except (struct.error, IndexError, ValueError) as e:
        return MidiCheck(False, f"Malformed MIDI structure: {e}")

    if track_count == 0:
        return MidiCheck(False, "No MTrk chunks found")
    if track_count != declared_tracks:
        return MidiCheck(False, "MIDI header track count does not match MTrk chunks")

    if smpte:
        fps = division & 0x7F
        if fps == 29:  # 29.97 drop-frame
            fps = 30
        duration = max_ticks / fps
    else:
        duration = max_ticks * _DEFAULT_US_PER_QUARTER / division / 1e6

    if duration <= 0:
        return MidiCheck(False, "MIDI duration is zero (no musical content)")
    if sounding_events == 0:
        return MidiCheck(False, "MIDI contains no sounding note events")
    return MidiCheck(
        True,
        duration_s=round(duration, 4),
        tracks=track_count,
        format=midi_format,
        division=division,
    )


def make_midi(ticks: int = 96, note: int = 60, velocity: int = 64) -> bytes:
    """Build a minimal valid single-track MIDI with one note.

    Duration = ``ticks`` quarters' worth at division 128 (e.g. 96 ticks ≈
    0.375 s at 120 BPM), so ``validate_midi`` accepts it.
    """

    def _vlq(value: int) -> bytes:
        out = bytearray()
        while value >= 0x80:
            out.insert(0, (value & 0x7F) | 0x80)
            value >>= 7
        out.insert(0, value)
        return bytes(out)

    track = (
        b"\x00"
        + bytes([0x90, note, velocity])  # note-on (delta 0)
        + _vlq(ticks)
        + bytes([0x80, note, 0x00])  # note-off
        + b"\x00\xff\x2f\x00"  # end of track
    )
    return (
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, 128)  # format 0, 1 track, div 128
        + b"MTrk"
        + struct.pack(">I", len(track))
        + track
    )
