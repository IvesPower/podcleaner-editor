import numpy as np
import pytest

from podcleaner_editor.analysis.activity import loud_intervals, noise_floor_db, own_speech
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


def test_bleed_is_not_own_speech():
    # A talks alone at -20 dBFS from 0 to 5 s; B picks up the bleed at -38 dBFS.
    lv_a = _levels(5, -20)
    lv_b = _levels(5, -38)
    assert own_speech([I(0, 5)], lv_b, lv_a, HOP, 10.0) == []


def test_speaker_keeps_own_speech_over_bleed():
    lv_a, lv_b = _levels(5, -20), _levels(5, -38)
    assert _pairs(own_speech([I(0, 5)], lv_a, lv_b, HOP, 10.0)) == [(0, 5)]


def test_real_overlap_is_own_speech_on_both():
    # A talks 0–5 s; B talks over it 2–3 s, both at -20 dBFS on their own mic.
    lv_a = _levels(5, -20)
    lv_b = _levels(5, -38, (2, 3, -20))
    assert _pairs(own_speech([I(2, 3)], lv_b, lv_a, HOP, 10.0)) == [(2, 3)]
    assert _pairs(own_speech([I(0, 5)], lv_a, lv_b, HOP, 10.0)) == [(0, 5)]


def test_own_speech_stays_inside_the_vad_intervals():
    lv_a, lv_b = _levels(10, -20), _levels(10, -60)
    assert _pairs(own_speech([I(1, 2), I(6, 7.5)], lv_a, lv_b, HOP, 10.0)) == [(1, 2), (6, 7.5)]


def test_noise_floor_and_loud_intervals():
    # Noise at -60 dBFS, a laugh at -30 dBFS from 4 to 5.5 s.
    levels = _levels(20, -60, (4, 5.5, -30))
    floor = noise_floor_db(levels)
    assert floor == pytest.approx(-60, abs=0.5)
    assert _pairs(loud_intervals(levels, HOP, floor + 12)) == [(4, 5.5)]


def test_noise_floor_ignores_digital_silence():
    # A track gated to digital silence most of the time, with room noise at -65 dBFS.
    levels = _levels(20, -120.0, (2, 6, -65), (6, 7, -25), (10, 14, -65))
    assert noise_floor_db(levels) == pytest.approx(-65, abs=0.5)


def test_noise_floor_of_a_silent_track():
    assert noise_floor_db(_levels(5, -120.0)) == -120.0


def test_loud_intervals_of_nothing():
    assert loud_intervals(_levels(5, -60), HOP, -48) == []
