"""The gain of the gate over a block of samples."""

from bisect import bisect_left, bisect_right

import numpy as np

from podcleaner_editor.timeline import Interval


def gate_gain(
    open_passages: list[Interval],
    first: int,
    count: int,
    rate: int,
    attack_s: float,
    release_s: float,
) -> np.ndarray:
    """Gain (float32) of samples `[first, first + count)`: 1 in a passage, 0 far from any.

    The gain rises linearly over `attack_s` before a passage and falls linearly over
    `release_s` after it; where two ramps overlap the larger gain wins. `open_passages`
    must be sorted and disjoint. Only the passages whose ramps touch the block are used.
    """
    gain = np.zeros(count, dtype=np.float32)
    block_start = first / rate
    block_end = (first + count) / rate
    low = bisect_right(open_passages, block_start - release_s, key=lambda p: p.end)
    high = bisect_left(open_passages, block_end + attack_s, key=lambda p: p.start)
    if low >= high:
        return gain
    times = (np.arange(first, first + count) / rate).astype(np.float64)
    attack = max(attack_s, 1e-9)
    release = max(release_s, 1e-9)
    for passage in open_passages[low:high]:
        rising = (times - (passage.start - attack_s)) / attack
        falling = ((passage.end + release_s) - times) / release
        np.maximum(gain, np.clip(np.minimum(rising, falling), 0.0, 1.0), out=gain)
    return gain
