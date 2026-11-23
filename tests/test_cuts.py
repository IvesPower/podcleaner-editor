import numpy as np

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.detect.cuts import (
    blocking_reason,
    cut_window,
    latest_ends,
    snap_to_quiet,
    words_overlap,
)
from podcleaner_editor.timeline import Interval as I

HOP = 0.01


def test_cut_window_stops_at_neighbours():
    assert cut_window(I(5.0, 5.4), prev_end=4.98, next_start=5.6, pad=0.05) == I(4.98, 5.45)
    assert cut_window(I(5.0, 5.4), prev_end=4.0, next_start=5.42, pad=0.05) == I(4.95, 5.42)


def test_cut_window_without_neighbours():
    assert cut_window(I(0.02, 0.4), None, None, 0.05) == I(0.0, 0.45)


def test_snap_moves_edges_to_quiet_frames():
    levels = np.full(1000, -40.0)
    levels[494] = -90.0  # 0.06 s before the window start
    levels[548] = -90.0  # end edge at 5.49 cuts frame 548
    snapped = snap_to_quiet(I(5.0, 5.5), I(5.1, 5.4), levels, HOP, 0.08, I(0.0, 10.0))
    assert abs(snapped.start - 4.94) < 1e-6
    assert abs(snapped.end - 5.49) < 1e-6


def test_snap_start_never_enters_the_word():
    levels = np.full(1000, -40.0)
    levels[505] = -100.0  # inside the word, within reach of the unclamped search
    snapped = snap_to_quiet(I(5.0, 5.5), I(5.02, 5.4), levels, HOP, 0.08, I(0.0, 10.0))
    assert snapped.start <= 5.02


def test_snap_end_never_enters_the_word():
    levels = np.full(1000, -40.0)
    levels[537] = -100.0  # the end edge at 5.38 would cut into the word
    snapped = snap_to_quiet(I(5.0, 5.45), I(5.02, 5.4), levels, HOP, 0.08, I(0.0, 10.0))
    assert snapped.end >= 5.4


def test_snap_start_stays_inside_bounds():
    levels = np.full(1000, -40.0)
    levels[495] = -100.0  # before the previous word's end, within reach of the unclamped search
    snapped = snap_to_quiet(I(4.98, 5.5), I(5.0, 5.4), levels, HOP, 0.08, I(4.98, 10.0))
    assert snapped.start == 4.98


def test_snap_end_stays_inside_bounds():
    levels = np.full(1000, -40.0)
    levels[545] = -100.0  # the end edge at 5.46 would pass the next word's start
    snapped = snap_to_quiet(I(4.9, 5.4), I(5.0, 5.3), levels, HOP, 0.08, I(0.0, 5.42))
    assert snapped.end <= 5.42


def test_snap_keeps_edge_without_levels():
    levels = np.full(100, -40.0)  # 1 s only
    snapped = snap_to_quiet(I(5.0, 5.5), I(5.1, 5.4), levels, HOP, 0.08, I(0.0, 10.0))
    assert snapped == I(5.0, 5.5)


def test_blocking_reason_order():
    w = I(5.0, 5.4)
    assert blocking_reason(w, [I(5.2, 5.3)], [I(5.0, 6.0)]) == "Other speech at the same time"
    assert blocking_reason(w, [], [I(5.0, 6.0)]) == "During a film clip"
    assert blocking_reason(w, [I(6.0, 7.0)], [I(7.0, 8.0)]) is None


def test_words_overlap_finds_a_long_earlier_word():
    words = [Word("long", 0.0, 5.2), Word("a", 1.0, 1.2), Word("b", 4.0, 4.5), Word("c", 5.0, 5.4)]
    ends = latest_ends(words)
    assert words_overlap(words, 3, 3, I(4.95, 5.45), ends)  # "long" ends inside the window
    assert not words_overlap(words[1:], 2, 2, I(4.95, 5.45), latest_ends(words[1:]))
    assert words_overlap(words, 1, 2, I(1.0, 4.5), ends)  # "long" spans the whole window
