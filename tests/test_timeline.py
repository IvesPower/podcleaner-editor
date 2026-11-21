import pytest

from podcleaner_editor.timeline import Interval as I
from podcleaner_editor.timeline import format_tc, intersect, invert, merge, union


def test_merge_joins_close_intervals():
    assert merge([I(0, 1), I(1.2, 2), I(5, 6)], max_gap=0.3) == [I(0, 2), I(5, 6)]


def test_merge_sorts_and_joins_overlapping_intervals():
    assert merge([I(5, 6), I(0, 3), I(2, 4)]) == [I(0, 4), I(5, 6)]


def test_merge_keeps_gaps_wider_than_max_gap():
    assert merge([I(0, 1), I(1.5, 2)], max_gap=0.3) == [I(0, 1), I(1.5, 2)]


def test_union_and_intersect():
    assert union([I(0, 2)], [I(1, 3)]) == [I(0, 3)]
    assert intersect([I(0, 2), I(4, 6)], [I(1, 5)]) == [I(1, 2), I(4, 5)]


def test_intersect_without_overlap_is_empty():
    assert intersect([I(0, 1)], [I(2, 3)]) == []
    assert intersect([I(0, 1)], [I(1, 2)]) == []


def test_invert_returns_gaps_within_total():
    assert invert([I(1, 2), I(3, 4)], total=5) == [I(0, 1), I(2, 3), I(4, 5)]
    assert invert([], total=5) == [I(0, 5)]


def test_invert_with_intervals_touching_the_edges():
    assert invert([I(0, 2), I(1, 5)], total=5) == []


def test_format_tc():
    assert format_tc(0) == "00:00:00.000"
    assert format_tc(7803.4567) == "02:10:03.457"


def test_format_tc_carries_rounded_milliseconds():
    assert format_tc(59.9996) == "00:01:00.000"


def test_interval_rejects_negative_duration():
    with pytest.raises(ValueError):
        I(2, 1)


def test_interval_duration():
    assert I(1.5, 4).duration == 2.5
