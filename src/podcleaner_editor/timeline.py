"""Time intervals in seconds, the operations the detectors share, and timecode formatting."""

from collections.abc import Iterable
from dataclasses import dataclass

# Float sums like 1.2 - 1.0 are not exact: a gap this close to max_gap counts as within it.
_EPSILON = 1e-9


@dataclass(frozen=True, order=True)
class Interval:
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"Interval ends before it starts: {self.start} > {self.end}")

    @property
    def duration(self) -> float:
        return self.end - self.start


def merge(intervals: Iterable[Interval], max_gap: float = 0.0) -> list[Interval]:
    """Sorted intervals, with those that overlap or are at most `max_gap` apart joined."""
    merged: list[Interval] = []
    for current in sorted(intervals):
        if merged and current.start - merged[-1].end <= max_gap + _EPSILON:
            last = merged[-1]
            merged[-1] = Interval(last.start, max(last.end, current.end))
        else:
            merged.append(current)
    return merged


def union(*lists: Iterable[Interval]) -> list[Interval]:
    """Every moment covered by at least one of the lists."""
    return merge(interval for intervals in lists for interval in intervals)


def intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """Moments covered by both lists (touching intervals share no time)."""
    left, right = merge(a), merge(b)
    result: list[Interval] = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i].start, right[j].start)
        end = min(left[i].end, right[j].end)
        if start < end:
            result.append(Interval(start, end))
        if left[i].end < right[j].end:
            i += 1
        else:
            j += 1
    return result


def subtract(a: list[Interval], b: list[Interval]) -> list[Interval]:
    """The moments of `a` not covered by `b`."""
    holes = merge(b)
    result: list[Interval] = []
    first = 0  # the first hole that can still meet an interval: both lists are sorted
    for interval in merge(a):
        while first < len(holes) and holes[first].end <= interval.start:
            first += 1
        cursor = interval.start
        k = first
        while k < len(holes) and holes[k].start < interval.end:
            if holes[k].start > cursor:
                result.append(Interval(cursor, holes[k].start))
            cursor = max(cursor, holes[k].end)
            k += 1
        if cursor < interval.end:
            result.append(Interval(cursor, interval.end))
    return result


def invert(intervals: list[Interval], total: float) -> list[Interval]:
    """The gaps between the intervals, within [0, total]."""
    gaps: list[Interval] = []
    cursor = 0.0
    for interval in merge(intervals):
        if interval.start > cursor:
            gaps.append(Interval(cursor, min(interval.start, total)))
        cursor = max(cursor, interval.end)
        if cursor >= total:
            break
    if cursor < total:
        gaps.append(Interval(cursor, total))
    return gaps


def format_tc(seconds: float) -> str:
    """`HH:MM:SS.mmm`, rounded to the millisecond."""
    total_ms = round(seconds * 1000)
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
