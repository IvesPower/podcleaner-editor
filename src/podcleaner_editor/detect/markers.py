"""Spoken instructions to Claude ("Dis Claude, on va couper ce passage-là.") heard in the
transcription."""

from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz

from podcleaner_editor.analysis.words import Word, normalize
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.cuts import (
    OTHER_SPEECH,
    blocking_reason,
    latest_ends,
    word_cut_window,
    words_overlap,
)
from podcleaner_editor.detect.fillers import is_filler
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.timeline import Interval

NO_CLEAR_END = "no clear end"

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


def _skipped(word: Word, settings: Settings) -> bool:
    """Punctuation alone or a hesitation: it does not stop the next word starting a sentence."""
    return not _tokens(word) or is_filler(word.text, settings.filler_words)


def _sentence_start(words: list[Word], i: int, settings: Settings) -> bool:
    """Word `i` begins a sentence: first word, after . ? ! …, or after a pause."""
    while i > 0:
        previous = words[i - 1]
        if _ends_sentence(previous) or words[i].start - previous.end >= settings.marker_pause_s:
            return True
        if not _skipped(previous, settings):
            return False
        i -= 1
    return True


def _start(words: list[Word], i: int, settings: Settings) -> int | None:
    """Where the instruction begins when word `i` is a call to Claude, or None.

    A call is "dis Claude" with "dis" at a sentence start, or "Claude" at a sentence start
    followed by a comma or a pause.
    """
    tokens = _tokens(words[i])
    trigger = normalize(settings.marker_trigger)
    if not tokens or fuzz.ratio(tokens[0], trigger) < settings.marker_min_score:
        return None
    previous = _tokens(words[i - 1]) if i > 0 else []
    if previous == [_CALL_WORD] and _sentence_start(words, i - 1, settings):
        return i - 1
    if not _sentence_start(words, i, settings):
        return None
    called = words[i].text.strip().endswith(",") or _pause_after(words, i, settings.marker_pause_s)
    return i if called else None


def _end(words: list[Word], first: int, trigger: int, settings: Settings) -> tuple[int, bool]:
    """The last word of the instruction that begins at `first`, and whether it ends clearly
    (sentence end, pause or last word) rather than at `marker_max_s`."""
    last = trigger
    for j in range(trigger + 1, len(words)):
        if words[j].end - words[first].start > settings.marker_max_s:
            return last, False
        last = j
        if _ends_sentence(words[j]) or _pause_after(words, j, settings.marker_pause_s):
            break
    return last, True


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
    """Every instruction to Claude with an action word; with `marker_cut_instructions`, cut
    unless something else is heard."""
    markers = []
    ends = latest_ends(words)
    i = 0
    while i < len(words):
        first = _start(words, i, settings)
        if first is None:
            i += 1
            continue
        last, clear_end = _end(words, first, i, settings)
        event_type = _event_type(words[first : last + 1], settings)
        if event_type is not None:
            markers.append(
                _marker(
                    words,
                    ends,
                    first,
                    last,
                    clear_end,
                    event_type,
                    track,
                    other_speech,
                    film,
                    levels,
                    settings,
                )
            )
        i = last + 1
    return markers


def _marker(
    words: list[Word],
    ends: list[float],
    first: int,
    last: int,
    clear_end: bool,
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
    if not settings.marker_cut_instructions:
        return Marker(Event(event_type, span.start, span.end, track, reason), None)
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
    blocked = None if clear_end else NO_CLEAR_END
    blocked = blocked or (OTHER_SPEECH if words_overlap(words, first, last, window, ends) else None)
    blocked = blocked or blocking_reason(window, other_speech, film)
    if blocked is not None:
        reason += f"; instruction kept: {blocked}"
    event = Event(event_type, span.start, span.end, track, reason)
    return Marker(event, None if blocked else window)
