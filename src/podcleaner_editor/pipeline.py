"""The analysis of an episode, from the tracks to the edit file."""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import soundfile as sf

from podcleaner_editor import __version__
from podcleaner_editor.analysis.activity import loud_intervals, noise_floor_db, own_speech
from podcleaner_editor.analysis.film import film_activity, film_clips
from podcleaner_editor.analysis.gate import gate_open
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
from podcleaner_editor.detect.fillers import INSIDE_INSTRUCTION, Filler, find_fillers
from podcleaner_editor.detect.markers import find_markers
from podcleaner_editor.detect.overlaps import find_overlap_attempts
from podcleaner_editor.detect.silences import find_silence_cuts
from podcleaner_editor.episode import Episode
from podcleaner_editor.errors import EditorError
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.render.markers import Marker, write_midi
from podcleaner_editor.render.splice import splice_plan
from podcleaner_editor.render.writer import RenderTrack, check_renderable, write_edit
from podcleaner_editor.report.markdown import AnalysisResult, render_edit_file
from podcleaner_editor.timeline import Interval, subtract, union

Decoder = Callable[[Path], np.ndarray]
Vad = Callable[[np.ndarray, Settings], list[Interval]]

_DOWNLOAD_NOTE = " (the Whisper model is downloaded on first use, about 1.6 GB)"
# Float sums are not exact: a piece this close to one level frame counts as one frame.
_EPSILON = 1e-9


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
        # Decoded a second time (after the VAD pass) so only one voice is in memory here.
        samples = decode(track.info.path)
        heard = transcribe_passages(samples, passages, transcriber)
        del samples  # free this voice before decoding the next one
        if episode.layout == "separate":
            heard = keep_own_words(heard, own_track, pad)
        if cache_path:
            try:
                save_words(cache_path, track.label, key, heard)
            except OSError as exc:
                raise EditorError(f"Could not write to {cache_path.parent}: {exc}") from exc
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


def _outside_instructions(fillers: list[Filler], marker_cuts: list[Interval]) -> list[Filler]:
    """The fillers, with those cut inside a spoken instruction's cut left to the instruction."""

    def inside(cut: Interval) -> bool:
        return any(m.start <= cut.start and cut.end <= m.end for m in marker_cuts)

    return [
        replace(f, cut=None, reason=INSIDE_INSTRUCTION) if f.cut and inside(f.cut) else f
        for f in fillers
    ]


def _silence_pieces(
    cuts: list[Interval], speech_cuts: list[Interval], hop: float
) -> tuple[list[Interval], int]:
    """What the speech cuts leave of the silence cuts, pieces of one level frame or less left
    out, and how many silences keep a piece.

    A silence the speech cuts already remove is reported with them, not as a silence.
    """
    pieces = [p for p in subtract(cuts, speech_cuts) if p.duration > hop + _EPSILON]
    shortened, k = 0, 0
    for cut in cuts:  # both lists are sorted and each piece lies in one cut
        kept = False
        while k < len(pieces) and pieces[k].start < cut.end:
            kept, k = True, k + 1
        shortened += kept
    return pieces, shortened


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
    del film  # only its levels are needed from here on

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
    fillers = _outside_instructions(fillers, marker_cuts)
    speech_cuts = [*(f.cut for f in fillers if f.cut is not None), *marker_cuts]

    progress("Looking for long silences…")
    loud = [_loud(levels, settings) for levels in voice_levels]
    activities = [subtract(x, speech_cuts) for x in [*own, *loud]]
    cuts = find_silence_cuts([*activities, film_on], episode.duration, settings)
    silence_cuts, shortened = _silence_pieces(cuts, speech_cuts, hop)

    gates = None
    if settings.gate_enabled:
        separate = episode.layout == "separate"
        gates = {
            track.label: tuple(
                gate_open(voice_levels[i], voice_levels[1 - i] if separate else None, hop, settings)
            )
            for i, track in enumerate(episode.voices)
        }

    return AnalysisResult(
        episode=episode,
        events=sorted(events, key=lambda e: (e.start, e.end)),
        silence_cuts=CutMap(tuple(silence_cuts)),
        silences_shortened=shortened,
        dry_run=True,
        fillers=tuple(fillers),
        marker_cuts=tuple(sorted(marker_cuts)),
        transcription=transcription,
        gates=gates,
    )


# Julien wants plain markers in Logic (Nov 26, 2026): the type only, the reasons stay in the
# edit file.
HESITATION_MARKER = "Hesitation"


def markers_of(result: AnalysisResult) -> list[Marker]:
    """A marker for each event and each flagged hesitation, at its time on the final audio,
    named by its type only."""
    cuts = result.cuts
    markers = [Marker(max(0.0, cuts.to_final(e.start)), str(e.type)) for e in result.events]
    markers += [
        Marker(max(0.0, cuts.to_final(f.word.start)), HESITATION_MARKER)
        for f in result.fillers
        if f.cut is None
    ]
    return sorted(markers, key=lambda m: m.time_s)


def file_slug(label: str) -> str:
    """`label` as a file name part: lowercase ASCII letters and digits joined by `-`."""
    ascii_text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "voice"


# Slugs of the film and mix outputs, which a voice must not take.
_TAKEN_SLUGS = frozenset({"film", "mix"})


def voice_slugs(labels: Sequence[str]) -> list[str]:
    """The slug of each label, numbered `-1`, `-2`… when several labels give the same one,
    or when it is the slug of the film or mix output."""
    slugs = [file_slug(label) for label in labels]
    counts = Counter(slugs)
    seen: Counter[str] = Counter()
    numbered = []
    for slug in slugs:
        if counts[slug] > 1 or slug in _TAKEN_SLUGS:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        numbered.append(slug)
    return numbered


def _render(
    result: AnalysisResult,
    settings: Settings,
    out_dir: Path,
    rate: int,
    progress: Callable[[str], None],
) -> list[Path]:
    """Write the edited tracks, their mix and the markers; return the files written."""
    episode = result.episode
    name = episode.name
    gates = result.gates
    tracks = [
        RenderTrack(
            track.info.path,
            out_dir / f"{name}.{slug}.wav",
            gates[track.label] if gates is not None else None,
        )
        for track, slug in zip(
            episode.voices, voice_slugs([t.label for t in episode.voices]), strict=True
        )
    ]
    tracks.append(RenderTrack(episode.film.info.path, out_dir / f"{name}.film.wav", None))
    mix = out_dir / f"{name}.mix.wav"
    midi = out_dir / f"{name}.markers.mid"

    n_total = round(episode.duration * rate)
    pieces = splice_plan(result.cuts, n_total, rate, settings.fade_ms)
    markers = markers_of(result)
    progress("Writing the edited tracks…")
    try:
        _, marked = write_edit(tracks, pieces, n_total, mix, settings, markers)
        if not marked:
            progress(f"⚠ The mix is over 4 GB (RF64): its markers are only in {midi.name}.")
        write_midi(markers, midi)
    except (OSError, sf.SoundFileError) as exc:
        raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
    return [*(t.target for t in tracks), mix, midi]


def run(
    episode: Episode,
    settings: Settings,
    out_dir: Path,
    *,
    dry_run: bool,
    progress: Callable[[str], None] = lambda _: None,
) -> list[Path]:
    """Analyses the episode and writes `<out_dir>/<name>.edit.md`, and without `dry_run` the
    edited tracks, their mix and the markers.

    Returns the edit file, then the other files written. The edit file is written last.
    """
    cache_path = out_dir / f"{episode.name}.words.json"
    path = out_dir / f"{episode.name}.edit.md"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)  # before the analysis, so it fails early
    except OSError as exc:
        raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
    # Before the analysis too: tracks that cannot be edited together fail at once.
    rate = None
    if not dry_run:
        try:
            rate = check_renderable([t.info.path for t in episode.tracks])
        except (OSError, sf.SoundFileError) as exc:
            raise EditorError(f"Could not open the tracks: {exc}") from exc
    result = analyze(episode, settings, cache_path=cache_path, progress=progress)
    outputs = [] if rate is None else _render(result, settings, out_dir, rate, progress)
    result = replace(result, dry_run=dry_run, outputs=tuple(outputs))
    try:
        path.write_text(render_edit_file(result, __version__, date.today()), encoding="utf-8")
    except OSError as exc:
        raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
    return [path, *outputs]
