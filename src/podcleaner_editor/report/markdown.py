"""The Markdown edit file: the timecodes to act on, then the report of what was done."""

from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path

from podcleaner_editor.analysis.transcribe import TranscriptionInfo
from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.detect.fillers import Filler
from podcleaner_editor.episode import Episode
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.timeline import Interval, format_tc, merge

_LAYOUT_NAMES = {"separate": "separate tracks", "mixed": "mixed voices"}
# A track this much longer than the episode or less is not said to be left out at the end.
_LEFT_OUT_MIN_S = 0.001


@dataclass(frozen=True)
class AnalysisResult:
    episode: Episode
    events: list[Event]
    silence_cuts: CutMap
    dry_run: bool
    fillers: tuple[Filler, ...] = ()
    marker_cuts: tuple[Interval, ...] = ()
    transcription: TranscriptionInfo | None = None
    # Silences shortened, when a speech cut splits some of them; None: one per silence cut.
    silences_shortened: int | None = None
    # Open passages of each voice's gate, by label; None: the gate is off.
    gates: dict[str, tuple[Interval, ...]] | None = None
    # The files written besides the edit file (filled in by `run`).
    outputs: tuple[Path, ...] = ()

    @cached_property
    def cuts(self) -> CutMap:
        """Every cut: silences, cut hesitations and spoken instructions."""
        filler_cuts = [f.cut for f in self.fillers if f.cut is not None]
        return CutMap(tuple(merge([*self.silence_cuts.cuts, *filler_cuts, *self.marker_cuts])))


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _timecodes(result: AnalysisResult) -> list[str]:
    events = sorted(result.events, key=lambda e: (e.start, e.end))
    if not events:
        return ["_No events._"]
    lines = [
        "| # | Type | Track | Original | Final | Duration | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for number, event in enumerate(events, start=1):
        cells = [
            str(number),
            str(event.type),
            _cell(event.track),
            format_tc(event.start),
            format_tc(result.cuts.to_final(event.start)),
            format_tc(event.end - event.start),
            _cell(event.reason),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _tracks(episode: Episode) -> list[str]:
    lines = [
        "| Track | File | Duration | Sample rate | Channels | Left out at the end |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for track in episode.tracks:
        info = track.info
        extra = info.duration - episode.duration
        cells = [
            _cell(track.label),
            _cell(info.path.name),
            format_tc(info.duration),
            f"{info.sample_rate} Hz",
            str(info.channels),
            format_tc(extra) if extra > _LEFT_OUT_MIN_S else "—",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _duration(result: AnalysisResult) -> str:
    cuts = result.cuts
    total = result.episode.duration
    return (
        f"Final duration: {format_tc(cuts.final_duration(total))} "
        f"(original: {format_tc(total)}), {format_tc(cuts.removed())} removed."
    )


def _files(result: AnalysisResult) -> list[str]:
    if result.dry_run:
        return ["None: dry run, no audio written."]
    return [f"- {path.name}" for path in result.outputs]


def _silences(result: AnalysisResult) -> str:
    cuts = result.silence_cuts
    count = len(cuts.cuts) if result.silences_shortened is None else result.silences_shortened
    return f"{_plural(count, 'silence')} shortened, {format_tc(cuts.removed())} removed."


_NOT_TRANSCRIBED = "Not available: the episode was not transcribed."


def _hesitations(result: AnalysisResult) -> list[str]:
    if result.transcription is None:
        return [_NOT_TRANSCRIBED]
    cut = [f.cut for f in result.fillers if f.cut is not None]
    flagged = sorted((f for f in result.fillers if f.cut is None), key=lambda f: f.word.start)
    removed = format_tc(sum(c.end - c.start for c in cut))
    head = f"{_plural(len(cut), 'hesitation')} removed ({removed}), {len(flagged)} flagged"
    if not flagged:
        return [head + "."]
    lines = [
        head + ":",
        "",
        "| Original | Final | Track | Context | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for filler in flagged:
        start = filler.word.start
        cells = [
            format_tc(start),
            format_tc(result.cuts.to_final(start)),
            _cell(filler.track),
            _cell(filler.context),
            _cell(filler.reason),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _markers(result: AnalysisResult) -> str:
    if result.transcription is None:
        return _NOT_TRANSCRIBED
    cut_requests = sum(1 for e in result.events if e.type == EventType.CUT_REQUEST)
    clips = sum(1 for e in result.events if e.type == EventType.CLIP_TO_ADD)
    if cut_requests + clips == 0:
        return "No spoken markers."
    clip_text = f"{clips} clip to add" if clips == 1 else f"{clips} clips to add"
    head = (
        f"{_plural(cut_requests + clips, 'spoken marker')}: "
        f"{_plural(cut_requests, 'requested cut')}, {clip_text}; "
    )
    if not result.marker_cuts:
        return head + "instructions left in the audio."
    removed = format_tc(sum(c.end - c.start for c in result.marker_cuts))
    return head + f"{_plural(len(result.marker_cuts), 'instruction')} removed ({removed})."


def _transcription(result: AnalysisResult) -> str:
    info = result.transcription
    if info is None:
        return "None."
    return (
        f"{info.backend} · {format_tc(info.speech_s)} of speech transcribed · "
        f"{info.cached_tracks} of {len(result.episode.voices)} tracks from the cache."
    )


def _overlaps(result: AnalysisResult) -> str:
    if result.episode.layout == "mixed":
        return "Not available: both voices are on one track."
    count = sum(1 for e in result.events if e.type == EventType.OVERLAP)
    return f"{_plural(count, 'attempt')} to take the floor flagged."


def render_edit_file(result: AnalysisResult, version: str, generated_on: date) -> str:
    episode = result.episode
    mode = "dry run" if result.dry_run else "edit"
    lines = [
        f"# {episode.name}: edit file",
        "",
        f"Generated by podcleaner-editor {version} on {generated_on.isoformat()}"
        f" · mode: {mode} · layout: {_LAYOUT_NAMES[episode.layout]}",
        "",
        "## Timecodes",
        "",
        *_timecodes(result),
        "",
        "## Report",
        "",
        "### Duration",
        "",
        _duration(result),
        "",
        "### Files",
        "",
        *_files(result),
        "",
        "### Tracks",
        "",
        *_tracks(episode),
        "",
        "### Silences",
        "",
        _silences(result),
        "",
        "### Hesitations",
        "",
        *_hesitations(result),
        "",
        "### Markers",
        "",
        _markers(result),
        "",
        "### Overlaps",
        "",
        _overlaps(result),
        "",
        "### Transcription",
        "",
        _transcription(result),
        "",
        "### Claude's opinions",
        "",
        "None: processed without Claude.",
    ]
    return "\n".join(lines) + "\n"
