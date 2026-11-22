"""Spoken markers ("Claude ici on veut couper") heard in the transcription."""

from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz

from podcleaner_editor.analysis.words import Word, normalize
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.cuts import blocking_reason, word_cut_window
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.timeline import Interval

# The last word of a phrase ("couper", "extrait") must be heard nearly right.
_LAST_WORD_MIN_SCORE = 70.0


@dataclass(frozen=True)
class Marker:
    """A spoken marker; `cut` is the phrase to remove from the audio, or `None` when it is kept."""

    event: Event
    cut: Interval | None


@dataclass(frozen=True)
class _Candidate:
    score: float
    first: int  # index of the first word
    last: int  # index of the last word
    event_type: EventType
    first_token: int


def _candidates(
    tokens: list[tuple[str, int]], phrase: str, event_type: EventType, min_score: float
) -> list[_Candidate]:
    target = normalize(phrase).split()
    if not target:
        return []
    found = []
    for size in (len(target) - 1, len(target), len(target) + 1):
        for i in range(len(tokens) - size + 1):
            window = tokens[i : i + size]
            if size < 1 or fuzz.ratio(window[-1][0], target[-1]) < _LAST_WORD_MIN_SCORE:
                continue
            score = fuzz.ratio(" ".join(t for t, _ in window), " ".join(target))
            if score >= min_score:
                found.append(_Candidate(score, window[0][1], window[-1][1], event_type, i))
    return found


def find_markers(
    words: list[Word],
    track: str,
    other_speech: list[Interval],
    film: list[Interval],
    levels: np.ndarray,
    settings: Settings,
) -> list[Marker]:
    """Every spoken marker on a track, with the phrase to cut unless something else is heard."""
    tokens = [(token, i) for i, word in enumerate(words) for token in normalize(word.text).split()]
    candidates = _candidates(
        tokens, settings.marker_cut_phrase, EventType.CUT_REQUEST, settings.marker_min_score
    ) + _candidates(
        tokens, settings.marker_clip_phrase, EventType.CLIP_TO_ADD, settings.marker_min_score
    )
    candidates.sort(key=lambda c: (-c.score, c.first_token))
    taken: set[int] = set()
    markers = []
    for c in candidates:
        indices = range(c.first, c.last + 1)
        if taken.intersection(indices):
            continue
        taken.update(indices)
        markers.append(_marker(words, c, track, other_speech, film, levels, settings))
    return sorted(markers, key=lambda m: m.event.start)


def _marker(
    words: list[Word],
    c: _Candidate,
    track: str,
    other_speech: list[Interval],
    film: list[Interval],
    levels: np.ndarray,
    settings: Settings,
) -> Marker:
    first, last = words[c.first], words[c.last]
    heard = " ".join(w.text.strip() for w in words[c.first : c.last + 1])
    reason = f'Spoken marker "{heard}" (score {int(round(c.score))})'
    span = Interval(first.start, last.end)
    window = word_cut_window(
        span,
        words[c.first - 1].end if c.first > 0 else None,
        words[c.last + 1].start if c.last + 1 < len(words) else None,
        settings.marker_pad_s,
        levels,
        settings.level_hop_s,
        settings.filler_snap_s,
    )
    cut: Interval | None = window
    blocked = blocking_reason(window, other_speech, film)
    if blocked is not None:
        cut = None
        reason += f"; phrase kept: {blocked}"
    return Marker(Event(c.event_type, first.start, last.end, track, reason), cut)
