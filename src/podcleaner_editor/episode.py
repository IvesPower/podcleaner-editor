"""An episode: one or two voice tracks and the film track, checked before any analysis."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from podcleaner_editor.audio_io import AudioInfo, probe
from podcleaner_editor.config import Layout, Settings
from podcleaner_editor.errors import EditorError
from podcleaner_editor.timeline import format_tc


@dataclass(frozen=True)
class Track:
    label: str
    info: AudioInfo


@dataclass(frozen=True)
class Episode:
    name: str
    voices: tuple[Track, ...]
    film: Track

    @property
    def layout(self) -> Layout:
        return "separate" if len(self.voices) == 2 else "mixed"

    @property
    def tracks(self) -> tuple[Track, ...]:
        return (*self.voices, self.film)

    @property
    def duration(self) -> float:
        return min(track.info.duration for track in self.tracks)


def _wav_info(path: Path) -> AudioInfo:
    info = probe(path)
    if info.container != "wav" or not info.codec.startswith("pcm_"):
        raise EditorError(f"WAV only: {path} is not an uncompressed WAV file")
    return info


def load_episode(voices: Sequence[Path], film: Path, name: str, settings: Settings) -> Episode:
    """Reads the files' facts; one voice file means both voices are mixed on it."""
    if len(voices) not in (1, 2):
        raise EditorError(f"Give 1 or 2 voice files, not {len(voices)}.")
    if len(voices) == 2:
        labels = list(settings.speakers)
    else:
        labels = [" + ".join(settings.speakers)]
    tracks = [Track(label, _wav_info(Path(p))) for label, p in zip(labels, voices, strict=True)]
    film_track = Track("Film", _wav_info(Path(film)))
    episode = Episode(name=name, voices=tuple(tracks), film=film_track)

    durations = [t.info.duration for t in episode.tracks]
    if max(durations) - min(durations) > settings.max_duration_mismatch_s:
        listed = ", ".join(
            f"{t.info.path.name} {format_tc(t.info.duration)}" for t in episode.tracks
        )
        raise EditorError(
            "The tracks do not have the same length "
            f"(more than {settings.max_duration_mismatch_s:g} s apart): {listed}. "
            "Were they recorded together?"
        )
    return episode
