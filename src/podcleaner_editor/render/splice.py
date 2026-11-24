"""The plan of kept pieces and crossfades, in samples of the original audio."""

import math
from dataclasses import dataclass

import numpy as np

from podcleaner_editor.cutmap import CutMap


@dataclass(frozen=True)
class Piece:
    """A kept piece `[start, end)` of the original, with the half-length of its fades.

    It is read over `[start - fade_in, end + fade_out)`; its first `2 * fade_in`
    samples rise and its last `2 * fade_out` samples fall. In the output it starts
    at the sum of the earlier pieces' lengths, minus `fade_in`.
    """

    start: int
    end: int
    fade_in: int
    fade_out: int


def _cut_samples(cuts: CutMap, n_total: int, rate: int) -> list[tuple[int, int]]:
    """The cuts as sample ranges, clamped, merged when they touch, without empty ones."""
    merged: list[tuple[int, int]] = []
    for cut in cuts.cuts:
        start = min(max(round(cut.start * rate), 0), n_total)
        end = min(max(round(cut.end * rate), 0), n_total)
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def splice_plan(cuts: CutMap, n_total: int, rate: int, fade_ms: int) -> list[Piece]:
    """The pieces kept between the cuts, with a shared crossfade at every join."""
    ranges: list[tuple[int, int]] = []
    position = 0
    for start, end in _cut_samples(cuts, n_total, rate):
        if start > position:
            ranges.append((position, start))
        position = end
    if position < n_total:
        ranges.append((position, n_total))

    fade = round(fade_ms / 1000 * rate / 2)
    fade_in = [0] * len(ranges)
    fade_out = [0] * len(ranges)
    for i in range(len(ranges) - 1):
        before, after = ranges[i], ranges[i + 1]
        h = min(
            fade,
            (after[0] - before[1]) // 2,
            (before[1] - before[0]) // 2,
            (after[1] - after[0]) // 2,
        )
        fade_out[i] = h
        fade_in[i + 1] = h
    return [Piece(s, e, fi, fo) for (s, e), fi, fo in zip(ranges, fade_in, fade_out, strict=True)]


def fade_curves(h: int) -> tuple[np.ndarray, np.ndarray]:
    """The incoming and outgoing equal-power gains (float32, length `2h`)."""
    x = (np.arange(2 * h) + 0.5) / (2 * h) if h > 0 else np.empty(0)
    return (
        np.sin(math.pi / 2 * x).astype(np.float32),
        np.cos(math.pi / 2 * x).astype(np.float32),
    )
