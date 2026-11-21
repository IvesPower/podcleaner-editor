"""Someone trying to talk over the other voice without taking the floor (separate tracks only)."""

from podcleaner_editor.config import Settings
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.timeline import Interval, intersect, merge

# Float sums are not exact: an overlap this close to the minimum counts as reaching it.
_EPSILON = 1e-9


def _attempts_by(
    speaker: list[Interval],
    holder: list[Interval],
    speaker_label: str,
    holder_label: str,
    settings: Settings,
) -> list[Event]:
    """Segments of `speaker` that start while `holder` talks, and `holder` keeps talking."""
    turns = merge(holder, settings.overlap_merge_gap_s)
    events: list[Event] = []
    for segment in merge(speaker):
        turn = next((t for t in turns if t.start < segment.start < t.end), None)
        if turn is None:  # the holder was not already talking when the speaker started
            continue
        overlap = sum(i.duration for i in intersect([segment], turns))
        if overlap + _EPSILON < settings.overlap_min_s:
            continue  # a backchannel ("yes", "mmh"), not an attempt
        keeps_floor = any(
            t.start <= segment.end and t.end >= segment.end + settings.overlap_floor_hold_s
            for t in turns
        )
        if keeps_floor:
            events.append(
                Event(
                    type=EventType.OVERLAP,
                    start=segment.start,
                    end=segment.end,
                    track=speaker_label,
                    reason=(
                        f"{speaker_label} tries to speak while {holder_label} is speaking; "
                        f"{holder_label} keeps the floor"
                    ),
                )
            )
    return events


def find_overlap_attempts(
    a: list[Interval], b: list[Interval], label_a: str, label_b: str, settings: Settings
) -> list[Event]:
    """Attempts to take the floor, both ways, sorted by start time."""
    events = _attempts_by(b, a, label_b, label_a, settings)
    events += _attempts_by(a, b, label_a, label_b, settings)
    return sorted(events, key=lambda e: e.start)
