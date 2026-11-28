"""A limiter linked across tracks: one gain for all of them, so their sum stays under a limit."""

import struct
from pathlib import Path

import numpy as np
import soundfile as sf

_MIX_CHANNELS = 2


def _samples(path: Path) -> np.ndarray:
    """The samples of a 32-bit float WAV file, mapped from disk and writable in place.

    libsndfile cannot update some headers (ffmpeg's) in place, and rewrites the header when it
    can, so the data chunk is mapped directly: only the samples change.
    """
    info = sf.info(path)
    if info.format != "WAV" or info.subtype != "FLOAT":
        raise ValueError(f"{path.name} is not a 32-bit float WAV file.")
    with path.open("rb") as f:
        if f.read(4) != b"RIFF" or f.read(8)[4:] != b"WAVE":
            raise ValueError(f"{path.name} is not a RIFF WAVE file.")
        while True:
            head = f.read(8)
            if len(head) < 8:
                raise ValueError(f"{path.name} has no data chunk.")
            chunk, size = head[:4], struct.unpack("<I", head[4:])[0]
            if chunk == b"data":
                offset = f.tell()
                break
            f.seek(size + size % 2, 1)
    shape = (info.frames, info.channels)
    return np.memmap(path, dtype="<f4", mode="r+", offset=offset, shape=shape)


def _stereo_sum(tracks: list[np.ndarray], first: int, count: int) -> np.ndarray:
    """The stereo sum of `[first, first + count)`, as the writer mixes it: mono copied to both
    channels, zeros past a track's end."""
    total = np.zeros((count, _MIX_CHANNELS), dtype=np.float32)
    for track in tracks:
        part = track[first : first + count]
        total[: len(part)] += part if part.shape[1] == _MIX_CHANNELS else part[:, :1]
    return total


def _over(
    tracks: list[np.ndarray], limit: float, block: int, scale: float
) -> tuple[np.ndarray, np.ndarray]:
    """The samples where the stereo sum of `tracks`, times `scale`, peaks above `limit`, and
    the gain that brings each of them back to it."""
    frames = max(len(track) for track in tracks)
    where, gains = [np.zeros(0, dtype=np.int64)], [np.zeros(0, dtype=np.float32)]
    for first in range(0, frames, block):
        total = _stereo_sum(tracks, first, min(block, frames - first))
        peak = scale * np.max(np.abs(total), axis=1)
        (hot,) = np.nonzero(peak > limit)
        where.append(hot + first)
        gains.append((limit / peak[hot]).astype(np.float32))
    return np.concatenate(where), np.concatenate(gains)


def _envelope(
    where: np.ndarray, gains: np.ndarray, first: int, count: int, half: int
) -> np.ndarray:
    """The smoothed gain over `[first, first + count)`: the lowest gain needed within
    `half` samples on each side, averaged over the same width, so it ramps down before a peak,
    back up after it, and is never above the gain a peak needs."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d  # imported late: slow

    margin = 2 * half
    needed = np.ones(count + 2 * margin, dtype=np.float32)
    inside = (where >= first - margin) & (where < first + count + margin)
    needed[where[inside] - first + margin] = gains[inside]
    size = 2 * half + 1
    held = minimum_filter1d(needed, size)
    smooth = np.minimum(uniform_filter1d(held, size), needed)
    return smooth[margin : margin + count]


def _scale(tracks: list[np.ndarray], first: int, gain: np.ndarray) -> None:
    """Multiply `[first, first + len(gain))` of every track by `gain`, in place."""
    for track in tracks:
        part = track[first : first + len(gain)]
        part *= gain[: len(part), None]


def link_limit(
    paths: list[Path],
    limit: float,
    gain_db: float = 0.0,
    block_s: float = 5.0,
    lookahead_s: float = 0.005,
) -> None:
    """Multiply every 32-bit float WAV file in place by `gain_db`, then lower them all by one
    shared gain wherever their stereo sum would peak above `limit` (a sample peak); with no
    gain, the files are left untouched away from those peaks.

    The gain ramps over `lookahead_s` on each side of a peak. Files are read block by block,
    never whole.
    """
    rate = sf.info(paths[0]).samplerate
    tracks = [_samples(path) for path in paths]
    try:
        block = max(1, int(block_s * rate))
        half = max(1, int(lookahead_s * rate))
        scale = 10 ** (gain_db / 20)
        where, gains = _over(tracks, limit, block, scale)
        frames = max(len(track) for track in tracks)
        for first in range(0, frames if len(where) or scale != 1.0 else 0, block):
            count = min(block, frames - first)
            near = (where >= first - 2 * half) & (where < first + count + 2 * half)
            if near.any():
                _scale(tracks, first, scale * _envelope(where, gains, first, count, half))
            elif scale != 1.0:
                _scale(tracks, first, np.full(count, scale, dtype=np.float32))
        for track in tracks:
            track.flush()
    finally:
        tracks.clear()  # the last reference to each map: closes it, so the file can be deleted
