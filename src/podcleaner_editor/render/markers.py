"""Markers for Logic Pro: a standard MIDI file and cue chunks in the mix WAV."""

import os
import struct
from dataclasses import dataclass
from pathlib import Path

MAX_NAME = 120
_DIVISION = 960
_TICKS_PER_S = 1920  # 120 bpm, 960 ticks per quarter note
_TEMPO = bytes([0x00, 0xFF, 0x51, 0x03, 0x07, 0xA1, 0x20])
_END_OF_TRACK = bytes([0x00, 0xFF, 0x2F, 0x00])
# Largest RIFF size a plain WAV file can declare.
_WAV_LIMIT = 0xFFFFFFFF


@dataclass(frozen=True)
class Marker:
    time_s: float
    name: str


def marker_name(kind: str, reason: str) -> str:
    """`"kind: reason"`, shortened to `MAX_NAME` characters with a final "…"."""
    name = f"{kind}: {reason}"
    if len(name) <= MAX_NAME:
        return name
    return name[: MAX_NAME - 1] + "…"


def _vlq(value: int) -> bytes:
    """MIDI variable-length quantity; a negative value counts as 0."""
    value = max(0, value)
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def write_midi(markers: list[Marker], path: Path) -> None:
    """Write a type 0 MIDI file with one marker meta event per marker."""
    track = bytearray(_TEMPO)
    tick = 0
    for marker in sorted(markers, key=lambda m: m.time_s):
        at = round(marker.time_s * _TICKS_PER_S)
        text = marker.name.encode("utf-8")
        track += _vlq(at - tick) + b"\xff\x06" + _vlq(len(text)) + text
        tick = at
    track += _END_OF_TRACK
    data = (
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, _DIVISION)
        + b"MTrk"
        + struct.pack(">I", len(track))
        + track
    )
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _chunk(chunk_id: bytes, body: bytes) -> bytes:
    pad = b"\x00" if len(body) % 2 else b""
    return chunk_id + struct.pack("<I", len(body)) + body + pad


def add_wav_markers(path: Path, markers: list[Marker], rate: int) -> bool:
    """Append `cue ` and `LIST adtl` chunks to a WAV; False, leaving it untouched, if it is
    RF64 or if the chunks would make it too large for a plain WAV."""
    if not markers:
        return True
    with open(path, "r+b") as f:
        if f.read(4) == b"RF64":
            return False
        cues = bytearray(struct.pack("<I", len(markers)))
        labels = bytearray(b"adtl")
        for k, marker in enumerate(markers, start=1):
            offset = round(marker.time_s * rate)
            cues += struct.pack("<II4sIII", k, offset, b"data", 0, 0, offset)
            text = marker.name.encode("utf-8") + b"\x00"
            labels += _chunk(b"labl", struct.pack("<I", k) + text)
        chunks = _chunk(b"cue ", bytes(cues)) + _chunk(b"LIST", bytes(labels))
        end = f.seek(0, os.SEEK_END)
        pad = b"\x00" if end % 2 else b""
        size = end + len(pad) + len(chunks)
        if size - 8 > _WAV_LIMIT:
            return False
        f.write(pad + chunks)
        f.seek(4)
        f.write(struct.pack("<I", size - 8))
    return True


def read_wav_markers(path: Path) -> list[tuple[int, str]]:
    """Markers of a WAV as `(position in samples, name)`, sorted by position."""
    data = path.read_bytes()
    positions: dict[int, int] = {}
    names: dict[int, str] = {}
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8 : pos + 8 + size]
        if chunk_id == b"cue ":
            count = struct.unpack_from("<I", body, 0)[0]
            for i in range(count):
                point = struct.unpack_from("<II4sIII", body, 4 + 24 * i)
                positions[point[0]] = point[5]
        elif chunk_id == b"LIST" and body[:4] == b"adtl":
            sub = 4
            while sub + 8 <= len(body):
                sub_size = struct.unpack_from("<I", body, sub + 4)[0]
                if body[sub : sub + 4] == b"labl":
                    label = body[sub + 8 : sub + 8 + sub_size]
                    ident = struct.unpack_from("<I", label, 0)[0]
                    names[ident] = label[4:].split(b"\x00", 1)[0].decode("utf-8")
                sub += 8 + sub_size + (sub_size % 2)
        pos += 8 + size + (size % 2)
    return sorted((positions[i], names[i]) for i in positions if i in names)
