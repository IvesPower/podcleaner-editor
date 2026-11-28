"""The ffmpeg filter step of the studio sound."""

from pathlib import Path

from podcleaner_editor.audio_io import _run
from podcleaner_editor.errors import EditorError


def apply_filters(source: Path, target: Path, filters: str) -> None:
    """Write `source` to `target` as 32-bit float WAV through the ffmpeg `filters` string.

    An empty `filters` copies the audio. Sample rate and channels are kept.
    """
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", source]
    if filters:
        args += ["-af", filters]
    args += ["-c:a", "pcm_f32le", "-f", "wav", target]
    done = _run(args)
    if done.returncode != 0:
        message = done.stderr.decode("utf-8", errors="replace").strip()
        raise EditorError(f"ffmpeg could not apply the sound filters: {message or 'ffmpeg failed'}")
