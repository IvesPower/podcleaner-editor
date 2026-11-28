"""Where a voice is open: the passages the gate lets through, from frame levels."""

import numpy as np

from podcleaner_editor.analysis.activity import mask_to_intervals
from podcleaner_editor.config import Settings
from podcleaner_editor.timeline import Interval, merge


def gate_open(
    levels: np.ndarray,
    other_levels: np.ndarray | None,
    hop_s: float,
    settings: Settings,
) -> list[Interval]:
    """The passages of one voice that stay open, in seconds.

    A frame is open when it is louder than `gate_threshold_db` and, given the other
    mic's levels, louder than that mic minus `bleed_margin_db` (the other voice's bleed
    stays shut). Closings shorter than `gate_min_silence_s` are filled. The passages are
    not widened: `gate_gain` applies the attack and the release.
    """
    frames = len(levels) if other_levels is None else min(len(levels), len(other_levels))
    opened = levels[:frames] > settings.gate_threshold_db
    if other_levels is not None:
        opened &= levels[:frames] > other_levels[:frames] - settings.bleed_margin_db
    return merge(mask_to_intervals(opened, hop_s), settings.gate_min_silence_s)
