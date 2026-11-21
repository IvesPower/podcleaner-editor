"""Long silences where every track is quiet, and the part of each to cut out."""

from podcleaner_editor.config import Settings
from podcleaner_editor.timeline import Interval, invert, union

# A gap this close to silence_min_s is not longer than it (float sums are not exact).
_EPSILON = 1e-9


def find_silence_cuts(
    activities: list[list[Interval]], total: float, settings: Settings
) -> list[Interval]:
    """For each gap longer than `silence_min_s` in all the activities, the middle to remove.

    The activities are every reason not to cut: speech on each voice, loud sounds on each
    voice (laughs, breaths), the film playing. Each cut leaves `silence_target_s` of the
    gap, half on each side.
    """
    keep_each_side = settings.silence_target_s / 2
    cuts: list[Interval] = []
    for gap in invert(union(*activities), total):
        if gap.duration > settings.silence_min_s + _EPSILON:
            cuts.append(Interval(gap.start + keep_each_side, gap.end - keep_each_side))
    return cuts
