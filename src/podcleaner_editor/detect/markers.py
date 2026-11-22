"""Spoken instructions to Claude ("Dis Claude, on va couper ce passage-là.") heard in the
transcription."""

from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz

from podcleaner_editor.analysis.words import Word, normalize
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.cuts import OTHER_SPEECH, blocking_reason, word_cut_window
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.timeline import Interval

_SENTENCE_END = (".", "?", "!", "…")
# French on purpose: "dis Claude" ("say, Claude") opens an instruction.
_CALL_WORD = "dis"


@dataclass(frozen=True)
class Marker:
    """A spoken instruction; `cut` is what to remove from the audio, or `None` when it is kept."""

    event: Event
    cut: Interval | None


def _tokens(word: Word) -> list[str]:
    return normalize(word.text).split()


def _ends_sentence(word: Word) -> bool:
    return word.text.strip().endswith(_SENTENCE_END)


def _pause_after(words: list[Word], i: int, pause_s: float) -> bool:
    return i + 1 < len(words) and words[i + 1].start - words[i].end >= pause_s


def _start(words: list[Word], i: int, settings: Settings) -> int | None:
    """Where the instruction begins when word `i` is the trigger at a sentence start, or None."""
    tokens = _tokens(words[i])
    trigger = normalize(settings.marker_trigger)
    if not tokens or fuzz.ratio(tokens[0], trigger) < settings.marker_min_score:
        return None
    if i == 0:
        return i
    previous = _tokens(words[i - 1])
    if previous and previous[-1] == _CALL_WORD:
        return i - 1
    if _ends_sentence(words[i - 1]) or _pause_after(words, i - 1, settings.marker_pause_s):
        return i
    return None


def _end(words: list[Word], first: int, settings: Settings) -> int:
    """The last word of the instruction that begins at `first`."""
    last = first
    for j in range(first, len(words)):
        if words[j].end - words[first].start > settings.marker_max_s:
            break
        last = j
        if _ends_sentence(words[j]) or _pause_after(words, j, settings.marker_pause_s):
            break
    return last


def _overlapped(words: list[Word], first: int, last: int, window: Interval) -> bool:
    """Another word of the track is heard in the window, or two of the instruction's overlap."""
    inside = words[first : last + 1]
    if any(a.end > b.start for a, b in zip(inside, inside[1:], strict=False)):
        return True
    return any(
        w.start < window.end and w.end > window.start
        for k, w in enumerate(words)
        if not first <= k <= last
    )


def _event_type(words: list[Word], settings: Settings) -> EventType | None:
    cut = {normalize(w) for w in settings.marker_cut_words}
    clip = {normalize(w) for w in settings.marker_clip_words}
    for word in words:
        for token in _tokens(word):
            if token in cut:
                return EventType.CUT_REQUEST
            if token in clip:
                return EventType.CLIP_TO_ADD
    return None


def find_markers(
    words: list[Word],
    track: str,
    other_speech: list[Interval],
    film: list[Interval],
    levels: np.ndarray,
    settings: Settings,
) -> list[Marker]:
    """Every instruction to Claude with an action word, cut unless something else is heard."""
    markers = []
    i = 0
    while i < len(words):
        first = _start(words, i, settings)
        if first is None:
            i += 1
            continue
        last = _end(words, i, settings)
        event_type = _event_type(words[first : last + 1], settings)
        if event_type is not None:
            markers.append(
                _marker(words, first, last, event_type, track, other_speech, film, levels, settings)
            )
        i = last + 1
    return markers


def _marker(
    words: list[Word],
    first: int,
    last: int,
    event_type: EventType,
    track: str,
    other_speech: list[Interval],
    film: list[Interval],
    levels: np.ndarray,
    settings: Settings,
) -> Marker:
    heard = " ".join(w.text.strip() for w in words[first : last + 1])
    reason = f'Spoken instruction: "{heard}"'
    span = Interval(words[first].start, words[last].end)
    window = word_cut_window(
        span,
        words[first - 1].end if first > 0 else None,
        words[last + 1].start if last + 1 < len(words) else None,
        settings.marker_pad_s,
        levels,
        settings.level_hop_s,
        settings.filler_snap_s,
    )
    # Mixed layout: the other voice's words are on this track, around or inside the instruction.
    blocked = OTHER_SPEECH if _overlapped(words, first, last, window) else None
    blocked = blocked or blocking_reason(window, other_speech, film)
    if blocked is not None:
        reason += f"; instruction kept: {blocked}"
    event = Event(event_type, span.start, span.end, track, reason)
    return Marker(event, None if blocked else window)
