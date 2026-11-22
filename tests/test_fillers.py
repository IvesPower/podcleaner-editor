import numpy as np

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.fillers import find_fillers, is_filler
from podcleaner_editor.timeline import Interval as I

SETTINGS = Settings()
QUIET = {"Julien": np.full(1000, -60.0)}
WORDS = [Word("alors", 4.0, 4.6), Word("euh", 5.0, 5.4), Word("on", 5.8, 6.0)]


def _find(words=WORDS, other=(), film=()):
    return find_fillers(
        {"Julien": list(words)}, {"Julien": list(other)}, list(film), QUIET, SETTINGS
    )


def test_isolated_euh_is_cut():
    [f] = _find()
    assert f.cut is not None and f.cut.start <= 5.0 and f.cut.end >= 5.4
    assert f.reason == "Isolated hesitation"
    assert f.context == "alors [euh] on"
    assert f.track == "Julien"


def test_context_has_up_to_four_words_each_side():
    words = [Word(w, i, i + 0.5) for i, w in enumerate("a b c d e f".split())]
    words.insert(6, Word("euh", 6.0, 6.3))
    words += [Word(w, 7 + i, 7.5 + i) for i, w in enumerate("g h i j k".split())]
    [f] = _find(words)
    assert f.context == "c d e f [euh] g h i j"


def test_variants_count_as_fillers():
    assert is_filler("Euuuh…", SETTINGS.filler_words) and is_filler("Hum,", SETTINGS.filler_words)
    assert not is_filler("heureux", SETTINGS.filler_words)
    assert not is_filler("euh bon", SETTINGS.filler_words)


def test_euh_under_the_other_voice_is_flagged():
    [f] = _find(other=[I(5.2, 5.3)])
    assert f.cut is None and f.reason == "Other speech at the same time"


def test_euh_overlapping_a_word_on_the_same_track_is_flagged():
    words = [Word("alors", 4.0, 4.6), Word("euh", 5.0, 5.4), Word("on", 5.3, 6.0)]
    [f] = _find(words)
    assert f.cut is None and f.reason == "Other speech at the same time"


def test_euh_during_film_clip_is_flagged():
    [f] = _find(film=[I(5.1, 5.2)])
    assert f.cut is None and f.reason == "During a film clip"


def test_long_euh_is_flagged():
    [f] = _find([Word("alors", 1.0, 1.5), Word("euh", 2.0, 4.0)])
    assert f.cut is None and f.reason == "Too long to be sure it is a hesitation"


def test_fillers_sorted_by_time_across_tracks():
    words = {"B": [Word("euh", 2.0, 2.2)], "A": [Word("euh", 1.0, 1.2)]}
    levels = {"A": np.full(500, -60.0), "B": np.full(500, -60.0)}
    found = find_fillers(words, {"A": [], "B": []}, [], levels, SETTINGS)
    assert [f.track for f in found] == ["A", "B"]
