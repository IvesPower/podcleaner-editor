"""Hesitations ("euh") heard in the transcription, and which of them can be cut."""

import re
from dataclasses import dataclass

import numpy as np

from podcleaner_editor.analysis.words import Word, normalize
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.cuts import OTHER_SPEECH, blocking_reason, word_cut_window
from podcleaner_editor.timeline import Interval

CUT_REASON = "Isolated hesitation"
TOO_LONG = "Too long to be sure it is a hesitation"

_CONTEXT_WORDS = 4


@dataclass(frozen=True)
class Filler:
    """A hesitation word; `cut` is the interval to remove, or `None` when it is only flagged."""

    word: Word
    track: str
    context: str
    cut: Interval | None
    reason: str


def _collapse(text: str) -> str:
    return re.sub(r"(.)\1+", r"\1", text)


def is_filler(text: str, words: tuple[str, ...]) -> bool:
    """One word that is a hesitation, ignoring case, accents, punctuation and stretched letters."""
    token = normalize(text)
    if not token or " " in token:
        return False
    return _collapse(token) in {_collapse(normalize(w)) for w in words}


def _context(track_words: list[Word], index: int) -> str:
    before = [w.text.strip() for w in track_words[max(0, index - _CONTEXT_WORDS) : index]]
    after = [w.text.strip() for w in track_words[index + 1 : index + 1 + _CONTEXT_WORDS]]
    return " ".join([*before, f"[{track_words[index].text.strip()}]", *after])


def find_fillers(
    words: dict[str, list[Word]],
    other_speech: dict[str, list[Interval]],
    film: list[Interval],
    levels: dict[str, np.ndarray],
    settings: Settings,
) -> list[Filler]:
    """Every hesitation, cut when nothing else is heard in its window, flagged otherwise."""
    hop = settings.level_hop_s
    fillers: list[Filler] = []
    for track, track_words in words.items():
        for i, word in enumerate(track_words):
            if not is_filler(word.text, settings.filler_words):
                continue
            prev = track_words[i - 1] if i > 0 else None
            nxt = track_words[i + 1] if i + 1 < len(track_words) else None
            context = _context(track_words, i)
            cut: Interval | None = None
            if word.span.duration > settings.filler_max_s:
                reason = TOO_LONG
            elif any(
                j != i and other.start < word.end and other.end > word.start
                for j, other in enumerate(track_words)
            ):
                reason = OTHER_SPEECH
            else:
                window = word_cut_window(
                    word.span,
                    prev.end if prev else None,
                    nxt.start if nxt else None,
                    settings.filler_pad_s,
                    levels[track],
                    hop,
                    settings.filler_snap_s,
                )
                blocked = blocking_reason(window, other_speech.get(track, []), film)
                if blocked is None:
                    cut, reason = window, CUT_REASON
                else:
                    reason = blocked
            fillers.append(Filler(word, track, context, cut, reason))
    return sorted(fillers, key=lambda f: f.word.start)
