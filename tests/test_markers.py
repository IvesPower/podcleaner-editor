import numpy as np

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.markers import find_markers
from podcleaner_editor.events import EventType
from podcleaner_editor.timeline import Interval as I

SETTINGS = Settings()
QUIET = np.full(2000, -60.0)


def _words(text, t0=1.0):
    words = []
    for i, w in enumerate(text.split()):
        start = t0 + i * 0.4
        words.append(Word(w, start, start + 0.3))
    return words


def _find(text, other=()):
    words = _words(text)
    return words, find_markers(words, "Julien", list(other), [], QUIET, SETTINGS)


def test_cut_marker_with_punctuation():
    words, [m] = _find("bon Claude, ici on veut couper ! alors")
    assert m.event.type == EventType.CUT_REQUEST and m.event.track == "Julien"
    assert (m.event.start, m.event.end) == (words[1].start, words[5].end) and m.cut is not None
    assert m.event.reason == 'Spoken marker "Claude, ici on veut couper" (score 100)'


def test_clip_marker_is_not_also_a_cut():
    _, [m] = _find("claude ici on veut ajouter un extrait")
    assert m.event.type == EventType.CLIP_TO_ADD


def test_misheard_word_still_matches():
    _, [m] = _find("clode ici on veut couper")
    assert m.event.type == EventType.CUT_REQUEST


def test_dropped_word_still_matches():
    _, [m] = _find("claude on veut couper")
    assert m.event.type == EventType.CUT_REQUEST


def test_sentence_that_starts_like_a_marker_is_ignored():
    _, found = _find("claude ici on veut du café")
    assert found == []


def test_two_markers_in_a_row():
    _, found = _find("claude ici on veut couper claude ici on veut ajouter un extrait")
    assert [m.event.type for m in found] == [EventType.CUT_REQUEST, EventType.CLIP_TO_ADD]


def test_marker_under_other_speech_is_kept_in_audio():
    _, [m] = _find("claude ici on veut couper", other=[I(0.0, 10.0)])
    assert m.cut is None
    assert m.event.reason.endswith("; phrase kept: Other speech at the same time")
