"""The analysis of an episode, from the tracks to the edit file."""

import contextlib
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
from podcleaner_editor.render.splice import Piece, splice_plan
from podcleaner_editor.render.writer import (
    RenderTrack,
    check_renderable,
    check_space,
    write_edit,
)
from podcleaner_editor.report.markdown import AnalysisResult, SoundInfo, render_edit_file
from podcleaner_editor.sound.denoise import Denoiser, denoise_file, make_denoiser
from podcleaner_editor.sound.filters import apply_filters, limit_filter, limit_level
from podcleaner_editor.sound.limiter import link_limit
from podcleaner_editor.sound.loudness import SILENCE_LUFS, film_gain, measure, shared_gain
from podcleaner_editor.timeline import Interval, subtract, union

Decoder = Callable[[Path], np.ndarray]
Vad = Callable[[np.ndarray, Settings], list[Interval]]

_DOWNLOAD_NOTE = " (the Whisper model is downloaded on first use, about 1.6 GB)"
_DENOISER_NOTE = " (the DeepFilterNet model is downloaded on first use)"
# Room taken by a WAV header and its chunks, besides the samples.
_HEADER_BYTES = 4096
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


def _plan(result: AnalysisResult, settings: Settings, rate: int) -> tuple[int, list[Piece]]:
    """The episode's length in samples and the pieces of it to keep."""
    n_total = round(result.episode.duration * rate)
    return n_total, splice_plan(result.cuts, n_total, rate, settings.fade_ms)


def _sound_tmp(out_dir: Path, name: str, slug: str, step: str = "") -> Path:
    """A temporary sound file of a voice or of the film, in the output folder."""
    return out_dir / f".{name}.{slug}{step}.sound.tmp.wav"


def _float_bytes(source: Path) -> int:
    """Size of a 32-bit float copy of `source`, header included."""
    info = sf.info(source)
    return info.frames * info.channels * 4 + _HEADER_BYTES


def _process_voices(
    result: AnalysisResult,
    settings: Settings,
    out_dir: Path,
    temporaries: list[Path],
    denoiser: Denoiser | None,
    progress: Callable[[str], None],
) -> dict[str, Path]:
    """The studio sound of each voice in a float temporary, by label; every temporary
    created is added to `temporaries`."""
    episode = result.episode
    labels = [track.label for track in episode.voices]
    processed: dict[str, Path] = {}
    for i, (track, slug) in enumerate(zip(episode.voices, voice_slugs(labels), strict=True)):
        note = _DENOISER_NOTE if i == 0 and settings.sound_denoise else ""
        progress(f"Processing the sound of {track.label}…{note}")
        source = track.info.path
        target = _sound_tmp(out_dir, episode.name, slug)
        temporaries.append(target)
        if settings.sound_denoise:
            denoised = _sound_tmp(out_dir, episode.name, slug, ".denoised")
            temporaries.append(denoised)
            denoiser = denoiser or make_denoiser()
            denoise_file(source, denoised, denoiser)
            apply_filters(denoised, target, settings.sound_filters)
            with contextlib.suppress(OSError):  # else left to the caller's cleanup
                denoised.unlink(missing_ok=True)
        else:
            apply_filters(source, target, settings.sound_filters)
        processed[track.label] = target
    return processed


def _render(
    result: AnalysisResult,
    settings: Settings,
    out_dir: Path,
    pieces: list[Piece],
    n_total: int,
    progress: Callable[[str], None],
    processed: dict[str, Path] | None = None,
    gain_db: float = 0.0,
    film: Path | None = None,
) -> list[Path]:
    """Write the edited tracks, their mix and the markers, every track at `gain_db`; return
    the files written.

    A voice in `processed`, and the film when `film` is given, is cut from that copy, in its
    raw file's subtype.
    """
    episode = result.episode
    name = episode.name
    gates = result.gates
    processed = processed or {}
    tracks = [
        RenderTrack(
            processed.get(track.label, track.info.path),
            out_dir / f"{name}.{slug}.wav",
            gates[track.label] if gates is not None else None,
            sf.info(track.info.path).subtype,
        )
        for track, slug in zip(
            episode.voices, voice_slugs([t.label for t in episode.voices]), strict=True
        )
    ]
    raw_film = episode.film.info.path
    tracks.append(
        RenderTrack(film or raw_film, out_dir / f"{name}.film.wav", None, sf.info(raw_film).subtype)
    )
    mix = out_dir / f"{name}.mix.wav"
    midi = out_dir / f"{name}.markers.mid"

    markers = markers_of(result)
    progress("Writing the edited tracks…")
    try:
        _, marked = write_edit(tracks, pieces, n_total, mix, settings, markers, gain_db=gain_db)
        if not marked:
            progress(f"⚠ The mix is over 4 GB (RF64): its markers are only in {midi.name}.")
        write_midi(markers, midi)
    except (OSError, sf.SoundFileError) as exc:
        raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
    return [*(t.target for t in tracks), mix, midi]


def _level(
    result: AnalysisResult,
    settings: Settings,
    out_dir: Path,
    processed: dict[str, Path],
    temporaries: list[Path],
    gain_db: float,
    film_gain_db: float,
) -> tuple[list[Path], Path]:
    """Each processed voice at `gain_db`, and the raw film at `film_gain_db + gain_db`, through
    the limiter into float temporaries; return the voices' copies and the film's."""
    episode = result.episode
    labels = [track.label for track in episode.voices]
    voices = []
    for label, slug in zip(labels, voice_slugs(labels), strict=True):
        target = _sound_tmp(out_dir, episode.name, slug, ".limited")
        temporaries.append(target)
        apply_filters(processed[label], target, limit_filter(gain_db, settings.sound_true_peak_db))
        with contextlib.suppress(OSError):  # else left to the caller's cleanup
            processed[label].unlink(missing_ok=True)
        voices.append(target)
    film = _sound_tmp(out_dir, episode.name, "film")
    temporaries.append(film)
    chain = limit_filter(film_gain_db + gain_db, settings.sound_true_peak_db)
    apply_filters(episode.film.info.path, film, chain)
    return voices, film


def _render_with_sound(
    result: AnalysisResult,
    settings: Settings,
    out_dir: Path,
    rate: int,
    denoiser: Denoiser | None,
    progress: Callable[[str], None],
) -> tuple[list[Path], SoundInfo]:
    """Process the sound of each voice, bring the film to the voices' level, then every track
    to the target through the limiter, and write the edit at the small shared gain left;
    return the files written and what the sound stage did. The temporaries are always
    deleted."""
    episode = result.episode
    n_total, pieces = _plan(result, settings, rate)
    raw = [t.info.path for t in episode.tracks]
    # The processed voices, one more voice file at a time (denoised, or limited), the film.
    sizes = [_float_bytes(t.info.path) for t in episode.voices]
    extra = sum(sizes) + max(sizes) + _float_bytes(episode.film.info.path)
    check_space(raw, sum(p.end - p.start for p in pieces), out_dir, extra_bytes=extra)

    temporaries: list[Path] = []
    try:
        try:
            processed = _process_voices(result, settings, out_dir, temporaries, denoiser, progress)
        except (OSError, sf.SoundFileError) as exc:
            raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
        progress("Measuring the loudness…")
        # Before the write: once the audio is written, only its own measures remain.
        befores = [measure([path]) for path in raw] + [measure(raw)]
        voices = [processed[t.label] for t in episode.voices]
        raw_film = episode.film.info.path
        # The film to the voices' level first, so its loud clips do not hold the gain.
        clips = any(e.type == EventType.FILM_CLIP for e in result.events)
        fg = film_gain(measure(voices), befores[len(voices)], has_clips=clips)
        level = measure([*voices, raw_film], gains_db=[0.0] * len(voices) + [fg])
        gain = settings.sound_target_lufs - level.lufs if level.lufs > SILENCE_LUFS else 0.0
        progress("Levelling the tracks…")
        try:
            limited, film = _level(result, settings, out_dir, processed, temporaries, gain, fg)
            # The limiter took some loudness off the peaks: make it up, and lower all the
            # tracks as one where they peak together.
            level = measure([*limited, film])
            made_up = settings.sound_target_lufs - level.lufs if level.lufs > SILENCE_LUFS else 0.0
            limiter = link_limit(
                [*limited, film], limit_level(settings.sound_true_peak_db), made_up
            )
        except (OSError, sf.SoundFileError) as exc:
            raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
        # What is left is small, and still held by the true peak.
        rest, capped = shared_gain(
            measure([*limited, film]), settings.sound_target_lufs, settings.sound_true_peak_db
        )
        levelled = {t.label: path for t, path in zip(episode.voices, limited, strict=True)}
        outputs = _render(
            result, settings, out_dir, pieces, n_total, progress, levelled, rest, film
        )
    finally:
        for path in temporaries:
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)

    written = outputs[: len(raw) + 1]  # every track, then the mix
    progress("Measuring the loudness of the written files…")
    rows = tuple(
        (path.name, before, measure([path])) for path, before in zip(written, befores, strict=True)
    )
    chain = "DeepFilterNet 3 + filters" if settings.sound_denoise else "filters only"
    info = SoundInfo(
        chain,
        fg,
        gain + made_up + rest,
        capped,
        rows,
        settings.sound_target_lufs,
        settings.sound_true_peak_db,
        limiter,
    )
    return outputs, info


def run(
    episode: Episode,
    settings: Settings,
    out_dir: Path,
    *,
    dry_run: bool,
    progress: Callable[[str], None] = lambda _: None,
    denoiser: Denoiser | None = None,
) -> list[Path]:
    """Analyses the episode and writes `<out_dir>/<name>.edit.md`, and without `dry_run` the
    edited tracks, their mix and the markers.

    With `[sound] enabled`, each voice gets the studio sound first (the film only gets a gain),
    the film is brought to the voices' loudness, and every track is brought to the target through
    a limiter, so every file is written at one shared gain.
    `denoiser` defaults to `make_denoiser`, created only when a voice is denoised.

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
    outputs: list[Path] = []
    sound = None
    if rate is not None and settings.sound_enabled:
        outputs, sound = _render_with_sound(result, settings, out_dir, rate, denoiser, progress)
    elif rate is not None:
        n_total, pieces = _plan(result, settings, rate)
        outputs = _render(result, settings, out_dir, pieces, n_total, progress)
    result = replace(result, dry_run=dry_run, outputs=tuple(outputs), sound=sound)
    try:
        path.write_text(render_edit_file(result, __version__, date.today()), encoding="utf-8")
    except OSError as exc:
        raise EditorError(f"Could not write to {out_dir}: {exc}") from exc
    return [path, *outputs]
