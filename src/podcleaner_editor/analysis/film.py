"""Film clips played during the recording, found from activity on the dedicated film track."""

import numpy as np

from podcleaner_editor.analysis.activity import loud_intervals
from podcleaner_editor.timeline import Interval, merge

# Float sums are not exact: a clip this close to the minimum counts as reaching it.
_EPSILON = 1e-9


def film_activity(levels: np.ndarray, hop_s: float, threshold_dbfs: float) -> list[Interval]:
    """Where the film track plays (raw, every short burst kept): never a silence to cut."""
    return loud_intervals(levels, hop_s, threshold_dbfs)


def film_clips(activity: list[Interval], merge_gap_s: float, min_clip_s: float) -> list[Interval]:
    """Clips to report: activity with short pauses joined, very short bursts dropped."""
    joined = merge(activity, merge_gap_s)
    return [clip for clip in joined if clip.duration + _EPSILON >= min_clip_s]
