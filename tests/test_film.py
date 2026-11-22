from pathlib import Path

import numpy as np
import pytest

from podcleaner_editor.analysis.film import film_activity, film_clips
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k, frame_levels
from podcleaner_editor.timeline import Interval as I

HOP = 0.01
FILM = Path(__file__).resolve().parents[1] / "samples" / "pedit" / "pedit-full-piste-3-film.wav"


def _pairs(intervals):
    return [(round(i.start, 2), round(i.end, 2)) for i in intervals]


def test_film_activity_is_where_the_film_track_is_loud():
    levels = np.full(1000, -120.0)
    levels[200:500] = -20.0
    levels[600:610] = -50.0  # below the threshold
    assert _pairs(film_activity(levels, HOP, -45.0)) == [(2.0, 5.0)]


def test_clip_with_short_pause_is_one_clip():
    assert film_clips([I(10, 40), I(41.5, 70)], 2.0, 3.0) == [I(10, 70)]


def test_short_blip_is_ignored():
    assert film_clips([I(100, 101)], 2.0, 3.0) == []


def test_two_clips_far_apart():
    assert film_clips([I(10, 40), I(100, 130)], 2.0, 3.0) == [I(10, 40), I(100, 130)]


def test_blips_close_together_add_up_to_a_clip():
    assert film_clips([I(10, 11), I(12, 13), I(14, 15)], 2.0, 3.0) == [I(10, 15)]


@pytest.mark.slow
@pytest.mark.skipif(not FILM.is_file(), reason="samples/pedit/ is not available")
def test_the_test_recording_has_one_film_clip():
    levels = frame_levels(decode_mono_16k(FILM), ANALYSIS_RATE, HOP)
    clips = film_clips(film_activity(levels, HOP, -45.0), 2.0, 3.0)
    assert len(clips) == 1
    assert 59 < clips[0].start < 63 and 64 < clips[0].end < 68
