"""The analysis of an episode, from the tracks to the edit file."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np

from podcleaner_editor import __version__
from podcleaner_editor.analysis.activity import loud_intervals, noise_floor_db, own_speech
from podcleaner_editor.analysis.film import film_activity, film_clips
from podcleaner_editor.analysis.vad import speech_intervals
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k, frame_levels
from podcleaner_editor.config import Settings
from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.detect.overlaps import find_overlap_attempts
from podcleaner_editor.detect.silences import find_silence_cuts
from podcleaner_editor.episode import Episode
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.report.markdown import AnalysisResult, render_edit_file
from podcleaner_editor.timeline import Interval

Decoder = Callable[[Path], np.ndarray]
Vad = Callable[[np.ndarray, Settings], list[Interval]]


def _loud(levels: np.ndarray, settings: Settings) -> list[Interval]:
    """Sounds well above the track's background (laughs, breaths): never a silence."""
    threshold = noise_floor_db(levels) + settings.activity_above_floor_db
    return loud_intervals(levels, settings.level_hop_s, threshold)


def analyze(
    episode: Episode,
    settings: Settings,
    *,
    decode: Decoder | None = None,
    vad: Vad | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> AnalysisResult:
    """Finds the film clips, the silences to shorten and (separate tracks) the overlaps."""
    decode = decode or decode_mono_16k
    vad = vad or speech_intervals  # looked up at call time, so tests can replace it
    hop = settings.level_hop_s

    progress("Decoding the tracks…")
    voices = [decode(track.info.path) for track in episode.voices]
    film = decode(episode.film.info.path)
    voice_levels = [frame_levels(x, ANALYSIS_RATE, hop) for x in voices]
    film_levels = frame_levels(film, ANALYSIS_RATE, hop)

    progress("Detecting speech…")
    speech = [vad(x, settings) for x in voices]
    del voices  # the decoded voices are no longer needed: free them before the rest

    events: list[Event] = []
    if episode.layout == "separate":
        margin, gap = settings.bleed_margin_db, settings.own_speech_gap_s
        own = [
            own_speech(speech[0], voice_levels[0], voice_levels[1], hop, margin, gap),
            own_speech(speech[1], voice_levels[1], voice_levels[0], hop, margin, gap),
        ]
        progress("Looking for overlaps…")
        labels = [track.label for track in episode.voices]
        events += find_overlap_attempts(own[0], own[1], labels[0], labels[1], settings)
    else:
        own = speech  # one track holds both voices: no bleed to remove, no overlap to find

    progress("Looking for film clips…")
    film_on = film_activity(film_levels, hop, settings.film_threshold_dbfs)
    for clip in film_clips(film_on, settings.film_merge_gap_s, settings.film_min_clip_s):
        events.append(
            Event(
                EventType.FILM_CLIP,
                clip.start,
                clip.end,
                episode.film.label,
                "Activity on the film track",
            )
        )

    progress("Looking for long silences…")
    loud = [_loud(levels, settings) for levels in voice_levels]
    cuts = find_silence_cuts([*own, *loud, film_on], episode.duration, settings)

    return AnalysisResult(
        episode=episode,
        events=sorted(events, key=lambda e: (e.start, e.end)),
        silence_cuts=CutMap(tuple(cuts)),
        dry_run=True,
    )


def run(
    episode: Episode,
    settings: Settings,
    out_dir: Path,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> Path:
    """Analyses the episode and writes `<out_dir>/<name>.edit.md`; returns its path."""
    result = analyze(episode, settings, progress=progress)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{episode.name}.edit.md"
    path.write_text(render_edit_file(result, __version__, date.today()), encoding="utf-8")
    return path
