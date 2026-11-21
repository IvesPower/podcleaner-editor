import pytest

from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.timeline import Interval as I


def test_cutmap_to_final():
    m = CutMap((I(10, 12), I(20, 25)))
    assert m.to_final(5) == 5 and m.to_final(15) == 13 and m.to_final(30) == 23
    assert m.to_final(11) == 10 and m.final_duration(40) == 33


def test_cutmap_at_cut_edges():
    m = CutMap((I(10, 12),))
    assert m.to_final(10) == 10
    assert m.to_final(12) == 10


def test_removed_is_the_total_cut_length():
    assert CutMap((I(10, 12), I(20, 25))).removed() == 7
    assert CutMap(()).removed() == 0


def test_empty_cutmap_changes_nothing():
    assert CutMap(()).to_final(42.5) == 42.5


def test_cutmap_sorts_cuts():
    assert CutMap((I(20, 25), I(10, 12))).cuts == (I(10, 12), I(20, 25))


def test_cutmap_rejects_overlapping_cuts():
    with pytest.raises(ValueError):
        CutMap((I(10, 12), I(11, 13)))
