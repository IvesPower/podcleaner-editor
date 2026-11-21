import pytest

from podcleaner_editor.config import Settings
from podcleaner_editor.detect.silences import find_silence_cuts
from podcleaner_editor.timeline import Interval as I


def _approx(intervals):
    return [(pytest.approx(i.start), pytest.approx(i.end)) for i in intervals]


def _pairs(intervals):
    return [(i.start, i.end) for i in intervals]


def test_long_silence_shortened_to_target():
    cuts = find_silence_cuts([[I(0, 10)], [I(13, 20)]], total=20, settings=Settings())
    assert _pairs(cuts) == _approx([I(10.2, 12.8)])  # 3 s gap → 0.4 s kept


def test_silence_of_exactly_one_second_is_kept():
    assert find_silence_cuts([[I(0, 10), I(11, 20)]], 20, Settings()) == []


def test_laugh_on_one_track_prevents_cut():
    # Voice A: speech 0–10 and 15–20; loud sounds on A (a laugh) 11.5–13.
    speech_a, loud_a = [I(0, 10), I(15, 20)], [I(11.5, 13)]
    cuts = find_silence_cuts([speech_a, loud_a], 20, Settings())
    assert _pairs(cuts) == _approx([I(10.2, 11.3), I(13.2, 14.8)])


def test_film_activity_prevents_cut():
    voices, film = [I(0, 10), I(15, 20)], [I(10, 15)]
    assert find_silence_cuts([voices, film], 20, Settings()) == []


def test_other_voice_speaking_prevents_cut():
    assert find_silence_cuts([[I(0, 10), I(15, 20)], [I(9, 16)]], 20, Settings()) == []


def test_silence_at_the_start_and_end_is_shortened_too():
    cuts = find_silence_cuts([[I(3, 17)]], 20, Settings())
    assert _pairs(cuts) == _approx([I(0.2, 2.8), I(17.2, 19.8)])


def test_no_activity_at_all_is_one_long_silence():
    assert _pairs(find_silence_cuts([[], []], 10, Settings())) == _approx([I(0.2, 9.8)])
