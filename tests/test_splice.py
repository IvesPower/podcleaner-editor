import numpy as np

from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.render.splice import Piece, fade_curves, splice_plan
from podcleaner_editor.timeline import Interval


def _plan(cuts, n_total=1000, rate=1000, fade_ms=30):
    return splice_plan(CutMap(tuple(Interval(a, b) for a, b in cuts)), n_total, rate, fade_ms)


def test_no_cut_is_one_piece():
    assert _plan([]) == [Piece(0, 1000, 0, 0)]


def test_one_cut_two_pieces_with_shared_fade():
    assert _plan([(0.4, 0.6)]) == [Piece(0, 400, 0, 15), Piece(600, 1000, 15, 0)]


def test_fade_shortened_by_a_short_cut_or_piece():
    short_cut = _plan([(0.4, 0.41)])
    assert short_cut == [Piece(0, 400, 0, 5), Piece(410, 1000, 5, 0)]
    short_piece = _plan([(0.2, 0.4), (0.408, 0.6)])
    assert short_piece[1] == Piece(400, 408, 4, 4)


def test_cut_at_start_and_end():
    plan = _plan([(0.0, 0.2), (0.9, 1.0)])
    assert plan == [Piece(200, 900, 0, 0)]


def test_zero_fade_gives_no_fades():
    assert _plan([(0.4, 0.6)], fade_ms=0) == [Piece(0, 400, 0, 0), Piece(600, 1000, 0, 0)]


def test_touching_cuts_after_rounding_are_merged():
    plan = _plan([(0.4, 0.4996), (0.5004, 0.6)], n_total=1000)
    assert plan == [Piece(0, 400, 0, 15), Piece(600, 1000, 15, 0)]


def test_output_length_is_exact():
    rng = np.random.default_rng(7)
    n_total, rate = 48000, 1000
    points = np.sort(rng.uniform(0, 48.0, 100))
    cuts = [(float(points[i]), float(points[i + 1])) for i in range(0, 100, 2)]
    plan = _plan(cuts, n_total=n_total, rate=rate, fade_ms=20)
    removed = sum(round(b * rate) - round(a * rate) for a, b in cuts)
    assert sum(p.end - p.start for p in plan) == n_total - removed
    for p in plan:
        assert p.fade_in <= (p.end - p.start) // 2
        assert p.fade_out <= (p.end - p.start) // 2


def test_fade_curves_keep_power():
    fade_in, fade_out = fade_curves(15)
    assert fade_in.shape == fade_out.shape == (30,)
    assert fade_in.dtype == np.float32
    np.testing.assert_allclose(fade_in**2 + fade_out**2, 1.0, atol=1e-6)
    assert np.all(np.diff(fade_in) > 0)
    assert np.all(np.diff(fade_out) < 0)


def test_fade_curves_zero_is_empty():
    fade_in, fade_out = fade_curves(0)
    assert len(fade_in) == len(fade_out) == 0
