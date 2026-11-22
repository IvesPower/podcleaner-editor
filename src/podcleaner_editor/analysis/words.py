"""Words heard in the audio, and the passages worth transcribing."""

import re
import unicodedata
from dataclasses import dataclass

from podcleaner_editor.timeline import Interval, merge


@dataclass(frozen=True)
class Word:
    """A transcribed word, in seconds on the original audio."""

    text: str
    start: float
    end: float

    @property
    def span(self) -> Interval:
        return Interval(self.start, self.end)


def normalize(text: str) -> str:
    """Lowercase, no accents, punctuation turned into single spaces."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", stripped).strip()


def speech_passages(
    speech: list[Interval], total: float, gap_s: float, pad_s: float
) -> list[Interval]:
    """Speech joined across gaps up to `gap_s`, widened by `pad_s`, within [0, total]."""
    padded = [
        Interval(max(0.0, p.start - pad_s), min(total, p.end + pad_s)) for p in merge(speech, gap_s)
    ]
    return merge(padded)


def keep_own_words(words: list[Word], own: list[Interval], tolerance: float) -> list[Word]:
    """The words whose middle falls inside an `own` interval widened by `tolerance`."""
    kept = []
    for word in words:
        middle = (word.start + word.end) / 2
        if any(i.start - tolerance <= middle <= i.end + tolerance for i in own):
            kept.append(word)
    return kept
