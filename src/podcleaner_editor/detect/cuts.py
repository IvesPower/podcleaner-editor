"""Cut windows around a word, shared by the hesitation and spoken-marker detectors."""

import math
from bisect import bisect_right
from itertools import accumulate

import numpy as np

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.timeline import Interval, intersect

OTHER_SPEECH = "Other speech at the same time"
FILM_CLIP = "During a film clip"

# Float sums are not exact: a frame boundary this close to a limit counts as inside it.
_EPSILON = 1e-9


def cut_window(
    span: Interval, prev_end: float | None, next_start: float | None, pad: float
) -> Interval:
    """`span` widened by `pad`, never past the previous word's end or the next word's start."""
    start = span.start - pad
    start = max(start, prev_end) if prev_end is not None else max(start, 0.0)
    end = span.end + pad
    if next_start is not None:
        end = min(end, next_start)
    return Interval(min(start, span.start), max(end, span.end))


def _best_frame(
    lo: float, hi: float, origin: float, levels: np.ndarray, hop_s: float, end_edge: bool
) -> float:
    """The frame boundary in [lo, hi] with the quietest frame (ties: closest to `origin`)."""
    first = math.ceil(lo / hop_s - _EPSILON)
    last = math.floor(hi / hop_s + _EPSILON)
    best: tuple[float, float, float] | None = None
    for k in range(first, last + 1):
        frame = k - 1 if end_edge else k  # an end edge cuts the frame just before it
        if not 0 <= frame < len(levels):
            continue
        t = min(max(k * hop_s, lo), hi)
        candidate = (float(levels[frame]), abs(t - origin), t)
        if best is None or candidate < best:
            best = candidate
    return origin if best is None else best[2]


def snap_to_quiet(
    window: Interval,
    span: Interval,
    levels: np.ndarray,
    hop_s: float,
    snap_s: float,
    bounds: Interval,
) -> Interval:
    """Each edge of `window` moved to the quietest frame within `snap_s`, outside `span`."""
    start = _best_frame(
        max(window.start - snap_s, bounds.start),
        min(window.start + snap_s, span.start),
        window.start,
        levels,
        hop_s,
        end_edge=False,
    )
    end = _best_frame(
        max(window.end - snap_s, span.end),
        min(window.end + snap_s, bounds.end),
        window.end,
        levels,
        hop_s,
        end_edge=True,
    )
    return Interval(start, end)


def blocking_reason(
    window: Interval, other_speech: list[Interval], film: list[Interval]
) -> str | None:
    """Why `window` cannot be cut (other speech first, then a film clip), or `None`."""
    if intersect([window], other_speech):
        return OTHER_SPEECH
    if intersect([window], film):
        return FILM_CLIP
    return None


def word_cut_window(
    span: Interval,
    prev_end: float | None,
    next_start: float | None,
    pad: float,
    levels: np.ndarray,
    hop_s: float,
    snap_s: float,
) -> Interval:
    """`cut_window` snapped to the quietest frames, within the gap around the neighbouring words."""
    bounds = Interval(
        prev_end if prev_end is not None else 0.0,
        next_start if next_start is not None else len(levels) * hop_s,
    )
    window = cut_window(span, prev_end, next_start, pad)
    return snap_to_quiet(window, span, levels, hop_s, snap_s, bounds)


def latest_ends(words: list[Word]) -> list[float]:
    """For each word (sorted by start), the latest end among it and the words before it."""
    return list(accumulate((w.end for w in words), max))


def words_overlap(
    words: list[Word], first: int, last: int, window: Interval, ends: list[float]
) -> bool:
    """A word outside `words[first:last + 1]` is heard in `window`, or two inside it overlap.

    `words` are sorted by start and `ends` is their `latest_ends`.
    """
    inside = words[first : last + 1]
    if any(a.end > b.start for a, b in zip(inside, inside[1:], strict=False)):
        return True
    k = bisect_right(ends, window.start)  # no word before k ends after the window starts
    while k < len(words) and words[k].start < window.end:
        if not first <= k <= last and words[k].end > window.start:
            return True
        k += 1
    return False
