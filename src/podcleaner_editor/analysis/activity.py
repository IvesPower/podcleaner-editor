"""Who is really speaking on each mic, and which sounds are loud enough to never be a silence.

Works on frame levels (dBFS, one value every `hop_s` seconds, from `audio_io.frame_levels`).
"""

import numpy as np

from podcleaner_editor.audio_io import LEVEL_FLOOR_DB
from podcleaner_editor.timeline import Interval, merge

# Frames at or below this are digital silence (a gated or edited track), not room noise.
_DIGITAL_SILENCE_DB = LEVEL_FLOOR_DB + 20


def mask_to_intervals(mask: np.ndarray, hop_s: float) -> list[Interval]:
    """Runs of True frames as intervals in seconds."""
    padded = np.concatenate(([False], mask.astype(bool), [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    starts, ends = edges[::2], edges[1::2]  # always paired: the padding closes every run
    return [Interval(float(s * hop_s), float(e * hop_s)) for s, e in zip(starts, ends, strict=True)]


def intervals_to_mask(intervals: list[Interval], frames: int, hop_s: float) -> np.ndarray:
    """Frames covered by the intervals."""
    mask = np.zeros(frames, dtype=bool)
    for interval in intervals:
        first = max(0, int(round(interval.start / hop_s)))
        last = min(frames, int(round(interval.end / hop_s)))
        mask[first:last] = True
    return mask


def own_speech(
    vad: list[Interval],
    levels: np.ndarray,
    other_levels: np.ndarray,
    hop_s: float,
    bleed_margin_db: float,
    max_gap: float = 0.0,
) -> list[Interval]:
    """The speech in `vad` that is this mic's own voice, not the other voice's bleed.

    A frame is kept when this mic is louder than the other mic minus `bleed_margin_db`:
    bleed reaches a mic much quieter than the voice reaches its own mic. The test runs
    frame by frame, so it drops the dips between syllables; gaps up to `max_gap` are
    closed again.
    """
    frames = min(len(levels), len(other_levels))
    speech = intervals_to_mask(vad, frames, hop_s)
    louder = levels[:frames] > other_levels[:frames] - bleed_margin_db
    return merge(mask_to_intervals(speech & louder, hop_s), max_gap)


def noise_floor_db(levels: np.ndarray) -> float:
    """The track's background level: 10th percentile, digital silence left out."""
    sound = levels[levels > _DIGITAL_SILENCE_DB]
    if sound.size == 0:
        return LEVEL_FLOOR_DB
    return float(np.percentile(sound, 10))


def loud_intervals(levels: np.ndarray, hop_s: float, threshold_db: float) -> list[Interval]:
    """Where the level is above `threshold_db`."""
    return mask_to_intervals(levels > threshold_db, hop_s)
