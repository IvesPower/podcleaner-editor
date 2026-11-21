"""The cuts made to the original audio, to map an original time onto the final audio."""

import bisect
from dataclasses import dataclass

from podcleaner_editor.timeline import Interval


@dataclass(frozen=True)
class CutMap:
    cuts: tuple[Interval, ...]

    def __post_init__(self) -> None:
        cuts = tuple(sorted(self.cuts))
        for previous, current in zip(cuts, cuts[1:], strict=False):
            if current.start < previous.end:
                raise ValueError(f"Cuts overlap: {previous} and {current}")
        object.__setattr__(self, "cuts", cuts)
        # Running total of the time removed before each cut, for to_final.
        removed_before = [0.0]
        for cut in cuts:
            removed_before.append(removed_before[-1] + cut.duration)
        object.__setattr__(self, "_removed_before", tuple(removed_before))
        object.__setattr__(self, "_starts", tuple(cut.start for cut in cuts))

    def to_final(self, t: float) -> float:
        """`t` on the final audio; a time inside a cut lands where the cut was made."""
        index = bisect.bisect_right(self._starts, t)  # cuts that start at or before t
        if index == 0:
            return t
        cut = self.cuts[index - 1]
        before = self._removed_before[index - 1]
        if t < cut.end:
            return cut.start - before
        return t - before - cut.duration

    def final_duration(self, total: float) -> float:
        return total - self.removed()

    def removed(self) -> float:
        return self._removed_before[-1]
