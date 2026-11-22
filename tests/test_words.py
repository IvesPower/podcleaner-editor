from podcleaner_editor.analysis.words import Word, keep_own_words, normalize, speech_passages
from podcleaner_editor.timeline import Interval as I


def test_normalize_strips_case_accents_and_punctuation():
    assert normalize("Claude, ici… On VEUT couper !") == "claude ici on veut couper"
    assert normalize("Été") == "ete" and normalize("aujourd'hui") == "aujourd hui"


def test_word_span():
    assert Word("oui", 1.0, 1.2).span == I(1.0, 1.2)


def test_speech_passages_merge_pad_and_clamp():
    passages = speech_passages([I(0.1, 2), I(2.5, 4), I(8, 9.9)], total=10, gap_s=1.0, pad_s=0.2)
    assert passages == [I(0, 4.2), I(7.8, 10)]


def test_keep_own_words_drops_bleed():
    words = [Word("oui", 1.0, 1.2), Word("non", 5.0, 5.2)]
    assert keep_own_words(words, [I(0.5, 2)], tolerance=0.2) == [words[0]]
