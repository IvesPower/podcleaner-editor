import numpy as np
import pytest

from podcleaner_editor.analysis.gate import gate_open
from podcleaner_editor.config import Settings
from podcleaner_editor.render.gain import gate_gain
from podcleaner_editor.timeline import Interval as I

HOP = 0.01


def _levels(total_s, base_db, *spans):
    """Levels every 10 ms at `base_db`, with (start, end, db) spans on top."""
    levels = np.full(int(round(total_s / HOP)), base_db, dtype=float)
    for start, end, db in spans:
        levels[int(round(start / HOP)) : int(round(end / HOP))] = db
    return levels


def _pairs(intervals):
    return [(round(i.start, 2), round(i.end, 2)) for i in intervals]


def test_gate_opens_above_threshold():
    levels = _levels(4.0, -60.0, (1.0, 2.0, -20.0))
    assert _pairs(gate_open(levels, None, HOP, Settings())) == [(1.0, 2.0)]


def test_gate_fills_short_closings():
    short = _levels(4.0, -60.0, (1.0, 2.0, -20.0), (2.3, 3.0, -20.0))
    assert _pairs(gate_open(short, None, HOP, Settings())) == [(1.0, 3.0)]
    long = _levels(4.0, -60.0, (1.0, 2.0, -20.0), (2.6, 3.0, -20.0))
    assert _pairs(gate_open(long, None, HOP, Settings())) == [(1.0, 2.0), (2.6, 3.0)]


def test_gate_ignores_bleed():
    levels = _levels(3.0, -25.0)
    other = _levels(3.0, -10.0)
    assert gate_open(levels, other, HOP, Settings()) == []
    assert _pairs(gate_open(levels, None, HOP, Settings())) == [(0.0, 3.0)]


def test_gate_gain_ramps():
    gain = gate_gain([I(1.0, 2.0)], 0, 3000, 1000, 0.01, 0.1)
    assert gain.dtype == np.float32
    assert len(gain) == 3000
    assert gain[990] == pytest.approx(0.0, abs=0.02)
    assert gain[995] == pytest.approx(0.5, abs=0.02)
    assert np.all(gain[1000:2000] == 1.0)
    assert gain[2050] == pytest.approx(0.5, abs=0.02)
    assert np.all(gain[2100:] == 0.0)
    assert np.all(gain[:990] == 0.0)


def test_gate_gain_overlapping_ramps_use_the_maximum():
    # The release of the first passage overlaps the attack of the second.
    gain = gate_gain([I(1.0, 2.0), I(2.05, 3.0)], 0, 3500, 1000, 0.1, 0.1)
    # Release of the first gives 0.6 here, attack of the second 0.9.
    assert gain[2040] == pytest.approx(0.9, abs=0.02)
    assert gain[2060] == 1.0


def test_gate_gain_on_a_block_matches_the_whole():
    passages = [I(1.0, 1.5), I(1.55, 2.0), I(2.5, 2.8)]
    whole = gate_gain(passages, 0, 3000, 1000, 0.01, 0.1)
    block = gate_gain(passages, 1234, 500, 1000, 0.01, 0.1)
    assert np.array_equal(whole[1234:1734], block)


def test_gate_gain_without_passages_is_silent():
    assert not gate_gain([], 0, 100, 1000, 0.01, 0.1).any()
