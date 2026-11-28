"""A limiter linked across tracks: one gain for all of them, so their sum stays under a limit."""

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import soundfile as sf

from podcleaner_editor.errors import EditorError

_MIX_CHANNELS = 2
_SAMPLE_BYTES = 4
# A gain this close to 1 is no reduction (float rounding of the smoothing).
_UNITY = 1 - 1e-6


@dataclass(frozen=True)
class LimiterReport:
    """What the linked limiter did: the passages it lowered, their total length in seconds,
    and the deepest reduction in dB (0.0: none)."""

    passages: int
    reduced_s: float
    deepest_db: float


@dataclass(frozen=True)
class _Wav:
    """Where the samples of a 32-bit float WAV file are, so they can be updated in place."""

    path: Path
    offset: int
    frames: int
    channels: int


def _wav(path: Path) -> _Wav:
    """The layout of a 32-bit float WAV file; `EditorError` for any other file.

    libsndfile cannot update some headers (ffmpeg's) in place, and rewrites the header when it
    can, so the data chunk is found here and only the samples are ever written.
    """
    unexpected = f"The sound temporary {path.name} is not a 32-bit float WAV file"
    info = sf.info(path)
    if info.format != "WAV" or info.subtype != "FLOAT":
        raise EditorError(f"{unexpected} ({info.format}, {info.subtype}).")
    with path.open("rb") as f:
        if f.read(4) != b"RIFF" or f.read(8)[4:] != b"WAVE":
            raise EditorError(f"{unexpected}: no RIFF WAVE header.")
        while True:
            head = f.read(8)
            if len(head) < 8:
                raise EditorError(f"{unexpected}: no data chunk.")
            chunk, size = head[:4], struct.unpack("<I", head[4:])[0]
            if chunk == b"data":
                return _Wav(path, f.tell(), info.frames, info.channels)
            f.seek(size + size % 2, 1)


def _read(f: BinaryIO, wav: _Wav, first: int, count: int) -> np.ndarray:
    """Frames `[first, first + count)` of `wav` from its open file `f`, fewer past its end."""
    own = max(0, min(count, wav.frames - first))
    f.seek(wav.offset + first * wav.channels * _SAMPLE_BYTES)
    data = np.frombuffer(f.read(own * wav.channels * _SAMPLE_BYTES), dtype="<f4")
    return data.reshape(-1, wav.channels)


def _peaks(wavs: list[_Wav], first: int, count: int) -> np.ndarray:
    """The peak of the stereo sum at each frame of `[first, first + count)`, as the writer
    mixes it: mono copied to both channels, zeros past a track's end."""
    total = np.zeros((count, _MIX_CHANNELS), dtype=np.float32)
    for wav in wavs:
        with wav.path.open("rb") as f:
            part = _read(f, wav, first, count)
        total[: len(part)] += part if part.shape[1] == _MIX_CHANNELS else part[:, :1]
    return np.max(np.abs(total), axis=1)


def _over(
    wavs: list[_Wav], frames: int, limit: float, block: int, scale: float
) -> tuple[np.ndarray, np.ndarray]:
    """The frames, in order, where the stereo sum of `wavs`, times `scale`, peaks above
    `limit`, and the gain that brings each of them back to it."""
    where, gains = [np.zeros(0, dtype=np.int64)], [np.zeros(0, dtype=np.float32)]
    for first in range(0, frames, block):
        peak = scale * _peaks(wavs, first, min(block, frames - first))
        (hot,) = np.nonzero(peak > limit)
        where.append(hot + first)
        gains.append((limit / peak[hot]).astype(np.float32))
    return np.concatenate(where), np.concatenate(gains)


def _envelope(
    where: np.ndarray, gains: np.ndarray, first: int, count: int, half: int
) -> np.ndarray:
    """The smoothed gain over `[first, first + count)`, from the peaks in `where` (already
    narrowed to that span and `2 * half` frames around it): the lowest gain needed within
    `half` frames on each side, averaged over the same width, so it ramps down before a peak,
    back up after it, and is never above the gain a peak needs."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d  # imported late: slow

    margin = 2 * half
    needed = np.ones(count + 2 * margin, dtype=np.float32)
    needed[where - first + margin] = gains
    size = 2 * half + 1
    held = minimum_filter1d(needed, size)
    smooth = np.minimum(uniform_filter1d(held, size), needed)
    return smooth[margin : margin + count]


def _scale(wavs: list[_Wav], first: int, gain: np.ndarray) -> None:
    """Multiply `[first, first + len(gain))` of every file by `gain`, in place."""
    for wav in wavs:
        with wav.path.open("r+b") as f:
            part = _read(f, wav, first, len(gain)) * gain[: wav.frames - first, None]
            f.seek(wav.offset + first * wav.channels * _SAMPLE_BYTES)
            f.write(part.astype("<f4").tobytes())


def _runs(reduced: np.ndarray, before: bool) -> int:
    """How many runs of True start in `reduced`, the frame before it being `before`."""
    starts = reduced[1:] & ~reduced[:-1]
    return int(starts.sum()) + int(bool(len(reduced)) and reduced[0] and not before)


def link_limit(
    paths: list[Path],
    limit: float,
    gain_db: float = 0.0,
    block_s: float = 5.0,
    lookahead_s: float = 0.005,
) -> LimiterReport:
    """Multiply every 32-bit float WAV file in place by `gain_db`, then lower them all by one
    shared gain wherever their stereo sum would peak above `limit` (a sample peak); with no
    gain, the files are left untouched away from those peaks. Returns what was lowered.

    The gain ramps over `lookahead_s` on each side of a peak. Files are read block by block,
    never whole, and each is opened only for the block at hand, so an error leaves none open.
    """
    wavs = [_wav(path) for path in paths]
    rate = sf.info(paths[0]).samplerate
    block = max(1, int(block_s * rate))
    half = max(1, int(lookahead_s * rate))
    scale = 10 ** (gain_db / 20)
    frames = max(wav.frames for wav in wavs)
    where, gains = _over(wavs, frames, limit, block, scale)
    passages, reduced, deepest, before = 0, 0, 1.0, False
    for first in range(0, frames if len(where) or scale != 1.0 else 0, block):
        count = min(block, frames - first)
        lo = np.searchsorted(where, first - 2 * half)
        hi = np.searchsorted(where, first + count + 2 * half)
        if lo == hi:
            before = False
            if scale != 1.0:
                _scale(wavs, first, np.full(count, scale, dtype=np.float32))
            continue
        envelope = _envelope(where[lo:hi], gains[lo:hi], first, count, half)
        lowered = envelope < _UNITY
        passages += _runs(lowered, before)
        reduced += int(lowered.sum())
        deepest = min(deepest, float(envelope.min()))
        before = bool(lowered[-1])
        _scale(wavs, first, scale * envelope)
    deepest_db = 20 * math.log10(deepest) if deepest < _UNITY else 0.0
    return LimiterReport(passages, reduced / rate, deepest_db)
