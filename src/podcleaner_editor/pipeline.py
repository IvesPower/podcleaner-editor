"""The analysis of an episode, from the tracks to the edit file."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np

from podcleaner_editor import __version__
from podcleaner_editor.analysis.activity import loud_intervals, noise_floor_db, own_speech
from podcleaner_editor.analysis.film import film_activity, film_clips
from podcleaner_editor.analysis.transcribe import (
    Transcriber,
    TranscriptionInfo,
    make_transcriber,
    transcribe_passages,
)
from podcleaner_editor.analysis.vad import speech_intervals
from podcleaner_editor.analysis.words import Word, keep_own_words, speech_passages
from podcleaner_editor.analysis.words_cache import cache_key, load_words, save_words
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k, frame_levels
from podcleaner_editor.config import Settings
from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.detect.fillers import find_fillers
from podcleaner_editor.detect.markers import find_markers
from podcleaner_editor.detect.overlaps import find_overlap_attempts
from podcleaner_editor.detect.silences import find_silence_cuts
from podcleaner_editor.episode import Episode
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.report.markdown import AnalysisResult, render_edit_file
from podcleaner_editor.timeline import Interval, subtract, union

Decoder = Callable[[Path], np.ndarray]
Vad = Callable[[np.ndarray, Settings], list[Interval]]

_DOWNLOAD_NOTE = " (the first run downloads the Whisper model, about 1.6 GB)"


def _loud(levels: np.ndarray, settings: Settings) -> list[Interval]:
    """Sounds well above the track's background (laughs, breaths): never a silence."""
    threshold = noise_floor_db(levels) + settings.activity_above_floor_db
    return loud_intervals(levels, settings.level_hop_s, threshold)


def _transcribe(
    episode: Episode,
    own: list[list[Interval]],
    settings: Settings,
    decode: Decoder,
    transcriber: Transcriber | None,
    cache_path: Path | None,
    progress: Callable[[str], None],
) -> tuple[dict[str, list[Word]], TranscriptionInfo]:
    """The words of each voice, from the cache or else transcribed, one track at a time."""
    words: dict[str, list[Word]] = {}
    speech_s, cached, transcribed = 0.0, 0, False
    gap, pad = settings.passage_gap_s, settings.passage_pad_s
    for track, own_track in zip(episode.voices, own, strict=True):
        passages = [
            p for p in speech_passages(own_track, episode.duration, gap, pad) if p.duration > 0
        ]
        speech_s += sum(p.duration for p in passages)
        message = f"Transcribing {track.label}…"
        if not passages:
            progress(message)
            words[track.label] = []
            continue
        key = cache_key(track.info.path, passages, settings) if cache_path else None
        found = load_words(cache_path, track.label, key) if cache_path and key else None
        if found is not None:
            progress(message)
            words[track.label] = found
            cached += 1
            continue
        progress(message if transcribed else message + _DOWNLOAD_NOTE)
        transcribed = True
        transcriber = transcriber or make_transcriber(settings)
        samples = decode(track.info.path)
        heard = transcribe_passages(samples, passages, transcriber)
        del samples  # free this voice before decoding the next one
        if episode.layout == "separate":
            heard = keep_own_words(heard, own_track, pad)
        if cache_path and key:
            save_words(cache_path, track.label, key, heard)
        words[track.label] = heard
    backend = transcriber.name if transcribed and transcriber else "cache"
    return words, TranscriptionInfo(backend, speech_s, cached)


def _other_speech(
    episode: Episode, own: list[list[Interval]], words: dict[str, list[Word]]
) -> dict[str, list[Interval]]:
    """For each voice, what the other voice says (its own speech and its words); none if mixed."""
    labels = [track.label for track in episode.voices]
    if episode.layout != "separate":
        return {label: [] for label in labels}
    heard = [union(own[i], [w.span for w in words[label]]) for i, label in enumerate(labels)]
    return {labels[0]: heard[1], labels[1]: heard[0]}


def analyze(
    episode: Episode,
    settings: Settings,
    *,
    decode: Decoder | None = None,
    vad: Vad | None = None,
    transcriber: Transcriber | None = None,
    cache_path: Path | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> AnalysisResult:
    """Finds the film clips, the hesitations, the spoken markers, the silences to shorten and
    (separate tracks) the overlaps.

    `transcriber` defaults to `make_transcriber`, created only when a track is not in the words
    cache at `cache_path` (`None`: no cache).
    """
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
    clips = film_clips(film_on, settings.film_merge_gap_s, settings.film_min_clip_s)
    for clip in clips:
        events.append(
            Event(
                EventType.FILM_CLIP,
                clip.start,
                clip.end,
                episode.film.label,
                "Activity on the film track",
            )
        )

    words, transcription = _transcribe(
        episode, own, settings, decode, transcriber, cache_path, progress
    )
    other = _other_speech(episode, own, words)
    levels = {track.label: voice_levels[i] for i, track in enumerate(episode.voices)}

    progress("Looking for hesitations and spoken markers…")
    fillers = find_fillers(words, other, clips, levels, settings)
    markers = [
        marker
        for label, track_words in words.items()
        for marker in find_markers(track_words, label, other[label], clips, levels[label], settings)
    ]
    events += [m.event for m in markers]
    marker_cuts = [m.cut for m in markers if m.cut is not None]
    speech_cuts = [*(f.cut for f in fillers if f.cut is not None), *marker_cuts]

    progress("Looking for long silences…")
    loud = [_loud(levels, settings) for levels in voice_levels]
    activities = [subtract(x, speech_cuts) for x in [*own, *loud]]
    cuts = find_silence_cuts([*activities, film_on], episode.duration, settings)

    return AnalysisResult(
        episode=episode,
        events=sorted(events, key=lambda e: (e.start, e.end)),
        silence_cuts=CutMap(tuple(cuts)),
        dry_run=True,
        fillers=tuple(fillers),
        marker_cuts=tuple(sorted(marker_cuts)),
        transcription=transcription,
    )


def run(
    episode: Episode,
    settings: Settings,
    out_dir: Path,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> Path:
    """Analyses the episode and writes `<out_dir>/<name>.edit.md`; returns its path."""
    cache_path = out_dir / f"{episode.name}.words.json"
    result = analyze(episode, settings, cache_path=cache_path, progress=progress)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{episode.name}.edit.md"
    path.write_text(render_edit_file(result, __version__, date.today()), encoding="utf-8")
    return path
