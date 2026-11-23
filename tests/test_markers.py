from dataclasses import replace

import numpy as np

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.markers import find_markers
from podcleaner_editor.events import EventType
from podcleaner_editor.timeline import Interval as I

SETTINGS = Settings()
QUIET = np.full(20000, -60.0)


def _words(text, t0=1.0):
    """Words of 0.3 s, 0.1 s apart; a "/" stands for a 0.6 s pause."""
    words, t = [], t0
    for w in text.split():
        if w == "/":
            t += 0.6
            continue
        words.append(Word(w, t, t + 0.3))
        t += 0.4
    return words


def _find(text, other=(), film=(), settings=SETTINGS):
    words = _words(text)
    return words, find_markers(words, "Julien", list(other), list(film), QUIET, settings)


def _heard(marker):
    return marker.event.reason.split('"')[1]


# The three instructions Julien gives on the test recording (samples/pedit).


def test_dis_claude_ajoute_is_a_clip_to_add():
    text = "/ Dis Claude, ici il faudrait qu 'on ajoute un passage de son, / est -ce que"
    words, [m] = _find(text)
    assert m.event.type == EventType.CLIP_TO_ADD and m.event.track == "Julien"
    assert (m.event.start, m.event.end) == (words[0].start, words[11].end)
    assert m.event.reason == (
        'Spoken instruction: "Dis Claude, ici il faudrait qu \'on ajoute un passage de son,"'
    )
    assert m.cut is not None


def test_dis_claude_on_va_couper_is_a_cut():
    text = "ici ? Euh, dis Claude, on va couper ce passage -là, les dix dernières secondes. D 'ail"
    _, [m] = _find(text)
    assert m.event.type == EventType.CUT_REQUEST
    assert _heard(m) == "dis Claude, on va couper ce passage -là, les dix dernières secondes."


def test_dis_claude_supprimer_is_a_cut():
    text = "« Euh, dis Claude, est -ce que tu peux supprimer la phrase juste avant… »"
    _, [m] = _find(text)
    assert m.event.type == EventType.CUT_REQUEST
    assert _heard(m) == "dis Claude, est -ce que tu peux supprimer la phrase juste avant…"


def test_spec_phrase_after_a_pause():
    words, [m] = _find("alors bon / Claude, ici on veut couper / voilà")
    assert m.event.type == EventType.CUT_REQUEST
    assert (m.event.start, m.event.end) == (words[2].start, words[6].end)


def test_claude_followed_by_a_pause_is_a_call():
    _, [m] = _find("Claude / ici on veut couper.")
    assert _heard(m) == "Claude ici on veut couper."


def test_claude_without_comma_or_pause_is_ignored():
    _, found = _find("alors bon / Claude ici on veut couper / voilà")
    assert found == []


def test_claude_as_a_first_name_is_ignored():
    _, found = _find("je parle du film. Claude Chabrol a coupé la scène finale.")
    assert found == []
    _, found = _find("Bon. Claude Lelouch, dans cet extrait…")
    assert found == []


def test_dis_mid_sentence_is_ignored():
    _, found = _find("je te le dis Claude, coupe ça.")
    assert found == []


def test_claude_after_a_sentence_ending_in_dis_is_a_call():
    _, [m] = _find("je te le dis. Claude, coupe ça.")
    assert _heard(m) == "Claude, coupe ça."


def test_claude_mid_sentence_is_ignored():
    _, found = _find("j'ai demandé à Claude de couper ça.")
    assert found == []


def test_instruction_without_action_word_is_ignored():
    _, found = _find("Bon. Claude, tu es là ? On continue.")
    assert found == []


def test_misheard_trigger_still_found():
    _, [m] = _find("Cloude, ici on veut couper.")  # score 83 against "claude"
    assert m.event.type == EventType.CUT_REQUEST
    _, found = _find("Clode, ici on veut couper.")  # score 73: below marker_min_score
    assert found == []


def test_instruction_ends_at_a_pause():
    _, [m] = _find("Claude, coupe ça / et puis on supprime le reste.")
    assert _heard(m) == "Claude, coupe ça"


def test_instruction_capped_at_max_s():
    settings = replace(SETTINGS, marker_max_s=1.2)  # three words: 1.1 s, four: 1.5 s
    _, found = _find("Claude, on va bien couper", settings=settings)
    assert found == []  # the action word comes after the cap
    _, [m] = _find("Claude, coupe tout ça maintenant", settings=settings)
    assert _heard(m) == "Claude, coupe tout"
    assert m.cut is None
    assert m.event.reason.endswith("; instruction kept: no clear end")


def test_max_s_counts_from_dis():
    settings = replace(SETTINGS, marker_max_s=1.2)
    _, [m] = _find("Dis Claude, coupe ça.", settings=settings)  # from Claude: 1.1 s
    assert _heard(m) == "Dis Claude, coupe"
    assert m.cut is None
    assert m.event.reason.endswith("; instruction kept: no clear end")


def test_two_instructions_in_a_row():
    _, found = _find("Claude, coupe ça. Claude, ajoute un extrait.")
    assert [m.event.type for m in found] == [EventType.CUT_REQUEST, EventType.CLIP_TO_ADD]


def test_instruction_under_other_speech_is_kept_in_audio():
    _, [m] = _find("Claude, ici on veut couper", other=[I(0.0, 10.0)])
    assert m.cut is None
    assert m.event.reason.endswith("; instruction kept: Other speech at the same time")


def test_instruction_during_a_film_clip_is_kept_in_audio():
    _, [m] = _find("Claude, ici on veut couper", film=[I(1.5, 2.0)])
    assert m.cut is None
    assert m.event.reason.endswith("; instruction kept: During a film clip")


def test_mixed_layout_word_inside_keeps_the_instruction():
    words = _words("Claude, coupe ça.")
    words.insert(2, Word("ouais", 1.5, 1.9))  # the other voice, on the same track
    [m] = find_markers(words, "Julien + Franck", [], [], QUIET, SETTINGS)
    assert m.cut is None
    assert m.event.reason.endswith("; instruction kept: Other speech at the same time")


def test_mixed_layout_word_in_the_window_keeps_the_instruction():
    words = [Word("ouais.", 0.7, 1.05), *_words("Claude, coupe ça.")]  # ends inside the pad
    [m] = find_markers(words, "Julien + Franck", [], [], QUIET, SETTINGS)
    assert m.cut is None
    assert m.event.reason.endswith("; instruction kept: Other speech at the same time")
