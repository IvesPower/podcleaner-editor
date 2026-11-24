"""Streaming the cut tracks and their stereo mix to disk, block by block."""

import contextlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from podcleaner_editor.config import Settings
from podcleaner_editor.errors import EditorError
from podcleaner_editor.render.gain import gate_gain
from podcleaner_editor.render.splice import Piece, fade_curves
from podcleaner_editor.timeline import Interval

# Longest stretch read or written at once, across all tracks.
_BLOCK_S = 5.0
# Room left for the WAV header and chunks besides the samples.
_HEADER_BYTES = 4096
# Largest data size a plain WAV file can declare.
_WAV_LIMIT = 0xFFFFFFFF
# Free space required, as a multiple of the estimated output size.
_SPACE_MARGIN = 1.05
_MIX_CHANNELS = 2
_MIX_SUBTYPE = "FLOAT"

_SUBTYPE_BYTES = {
    "PCM_S8": 1,
    "PCM_U8": 1,
    "PCM_16": 2,
    "PCM_24": 3,
    "PCM_32": 4,
    "FLOAT": 4,
    "DOUBLE": 8,
    "ULAW": 1,
    "ALAW": 1,
}
_FLOAT_SUBTYPES = {"FLOAT", "DOUBLE"}


@dataclass(frozen=True)
class RenderTrack:
    """A raw track to cut into `target`, with its gate's open passages (`None`: no gate)."""

    source: Path
    target: Path
    gate: tuple[Interval, ...] | None


def check_renderable(sources: list[Path]) -> int:
    """The sample rate the sources share; `EditorError` if they cannot be edited together."""
    infos = [(Path(source), sf.info(source)) for source in sources]
    for path, info in infos:
        if info.channels not in (1, 2):
            raise EditorError(
                f"{path.name} has {info.channels} channels: "
                "only mono or stereo tracks can be edited."
            )
    rates = {info.samplerate for _, info in infos}
    if len(rates) > 1:
        listed = ", ".join(f"{path.name}: {info.samplerate} Hz" for path, info in infos)
        raise EditorError(
            f"The tracks do not share one sample rate ({listed}): "
            "convert them to the same rate first."
        )
    return rates.pop()


def _sample_bytes(subtype: str) -> int:
    """Bytes per sample of a subtype; 4 when it is not a known one."""
    return _SUBTYPE_BYTES.get(subtype, 4)


def _file_bytes(n_out: int, channels: int, subtype: str) -> int:
    """Estimated size of a file of `n_out` frames, header included."""
    return n_out * channels * _sample_bytes(subtype) + _HEADER_BYTES


def _wav_format(n_out: int, channels: int, subtype: str) -> str:
    """`"RF64"` when the file would be too large for a plain WAV, else `"WAV"`."""
    return "RF64" if _file_bytes(n_out, channels, subtype) > _WAV_LIMIT else "WAV"


def estimate_bytes(sources: list[Path], n_out: int) -> int:
    """Estimated size of the cut tracks of `sources` and of their stereo float mix."""
    total = _file_bytes(n_out, _MIX_CHANNELS, _MIX_SUBTYPE)
    for source in sources:
        info = sf.info(source)
        total += _file_bytes(n_out, info.channels, info.subtype)
    return total


def _existing_folder(folder: Path) -> Path:
    """`folder`, or its nearest parent that exists."""
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    return folder


def _check_space(sources: list[Path], n_out: int, folder: Path) -> None:
    """`EditorError` when `folder` lacks the room for the outputs, with a margin."""
    estimate = estimate_bytes(sources, n_out)
    free = shutil.disk_usage(_existing_folder(folder)).free
    if free < _SPACE_MARGIN * estimate:
        raise EditorError(
            f"Not enough disk space in {folder}: about {estimate / 1e9:.1f} GB needed, "
            f"{free / 1e9:.1f} GB free."
        )


def _tmp_path(target: Path) -> Path:
    return target.with_name(target.name + ".tmp")


class _Track:
    """An open source and its temporary output, with the faded tail held for the next join."""

    def __init__(self, track: RenderTrack, n_out: int) -> None:
        self.gate = list(track.gate) if track.gate is not None else None
        self.tmp = _tmp_path(track.target)
        self.target = track.target
        self.held = np.zeros((0, 1), dtype=np.float32)
        self.reader = sf.SoundFile(track.source)
        self.channels = self.reader.channels
        subtype = self.reader.subtype
        self.clip = subtype not in _FLOAT_SUBTYPES
        try:
            self.output = sf.SoundFile(
                self.tmp,
                "w",
                samplerate=self.reader.samplerate,
                channels=self.channels,
                subtype=subtype,
                format=_wav_format(n_out, self.channels, subtype),
            )
        except BaseException:
            self.reader.close()
            raise

    def read(self, first: int, count: int) -> np.ndarray:
        """Samples `[first, first + count)` of the source, zeros past its end."""
        self.reader.seek(min(first, self.reader.frames))
        data = self.reader.read(count, dtype="float32", always_2d=True)
        if len(data) < count:
            data = np.concatenate(
                [data, np.zeros((count - len(data), self.channels), dtype=np.float32)]
            )
        return data

    def write(self, data: np.ndarray) -> None:
        self.output.write(np.clip(data, -1.0, 1.0) if self.clip else data)

    def close(self) -> None:
        self.reader.close()
        self.output.close()


def _as_stereo(data: np.ndarray) -> np.ndarray:
    return data if data.shape[1] == _MIX_CHANNELS else np.repeat(data, _MIX_CHANNELS, axis=1)


def _write_piece(
    piece: Piece,
    tracks: list[_Track],
    mix: sf.SoundFile,
    block: int,
    rate: int,
    settings: Settings,
) -> int:
    """Write one piece to every track and to the mix; return the frames written."""
    first = piece.start - piece.fade_in
    length = piece.end + piece.fade_out - first
    head = 2 * piece.fade_in
    tail_start = length - 2 * piece.fade_out
    rise, _ = fade_curves(piece.fade_in)
    _, fall = fade_curves(piece.fade_out)
    tails = [np.zeros((2 * piece.fade_out, t.channels), dtype=np.float32) for t in tracks]
    written = 0
    for a in range(0, length, block):
        b = min(a + block, length)
        mix_block: np.ndarray | None = None
        for track, tail in zip(tracks, tails, strict=True):
            data = track.read(first + a, b - a)
            if track.gate is not None:
                gain = gate_gain(
                    track.gate,
                    first + a,
                    b - a,
                    rate,
                    settings.gate_attack_s,
                    settings.gate_release_s,
                )
                data *= gain[:, None]
            # Positions within the piece, not within the block, index the fades.
            chunks: list[np.ndarray] = []
            if a < head:
                end = min(b, head)
                track.held[a:end] += data[: end - a] * rise[a:end, None]
                if end == head:
                    chunks.append(track.held)
            middle_a, middle_b = max(a, head), min(b, tail_start)
            if middle_a < middle_b:
                chunks.append(data[middle_a - a : middle_b - a])
            if b > tail_start:
                start = max(a, tail_start)
                tail[start - tail_start : b - tail_start] = (
                    data[start - a :] * fall[start - tail_start : b - tail_start, None]
                )
            out = np.concatenate(chunks) if chunks else data[:0]
            track.write(out)
            stereo = _as_stereo(out)
            mix_block = stereo if mix_block is None else mix_block + stereo
        if mix_block is not None:
            mix.write(mix_block)
            written += len(mix_block)
    for track, tail in zip(tracks, tails, strict=True):
        track.held = tail
    return written


def _discard(handles: list[sf.SoundFile | None], paths: list[Path]) -> None:
    """Close every handle and delete every path, going on past any failure."""
    for handle in handles:
        if handle is not None:
            with contextlib.suppress(Exception):
                handle.close()
    for path in paths:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def write_edit(
    tracks: list[RenderTrack],
    pieces: list[Piece],
    n_total: int,
    mix_target: Path,
    settings: Settings,
) -> int:
    """Write every cut track and their stereo mix in one streamed pass; return `n_out`.

    Each output is first written to `<target>.tmp`; the targets are replaced only at the
    end, once every file is written and closed. An error, or Ctrl+C, before that deletes
    the `.tmp` files and leaves the existing targets as they were. A failure while
    renaming can leave some targets new and some old, but never a half-written file.
    """
    sources = [track.source for track in tracks]
    rate = check_renderable(sources)
    n_out = sum(piece.end - piece.start for piece in pieces)
    if pieces and (pieces[0].start < 0 or pieces[-1].end > n_total):
        raise ValueError(f"Pieces fall outside [0, {n_total}).")
    _check_space(sources, n_out, mix_target.parent)

    block = max(1, int(_BLOCK_S * rate))
    opened: list[_Track] = []
    mix_tmp = _tmp_path(mix_target)
    mix: sf.SoundFile | None = None
    try:
        for track in tracks:
            opened.append(_Track(track, n_out))
        mix = sf.SoundFile(
            mix_tmp,
            "w",
            samplerate=rate,
            channels=_MIX_CHANNELS,
            subtype=_MIX_SUBTYPE,
            format=_wav_format(n_out, _MIX_CHANNELS, _MIX_SUBTYPE),
        )
        written = sum(_write_piece(p, opened, mix, block, rate, settings) for p in pieces)
        if written != n_out:
            raise RuntimeError(f"Wrote {written} frames instead of {n_out}.")
        for track in opened:
            track.close()
        mix.close()
    except BaseException:
        handles = [h for t in opened for h in (t.reader, t.output)] + [mix]
        _discard(handles, [_tmp_path(track.target) for track in tracks] + [mix_tmp])
        raise
    moves = [(track.tmp, track.target) for track in opened] + [(mix_tmp, mix_target)]
    try:
        for tmp, target in moves:
            os.replace(tmp, target)
    except BaseException:
        _discard([], [tmp for tmp, _ in moves])
        raise
    return n_out
