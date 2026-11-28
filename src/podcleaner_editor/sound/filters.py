"""The ffmpeg filter steps of the studio sound: the voice filters and the limiter."""

from pathlib import Path

from podcleaner_editor.audio_io import _run
from podcleaner_editor.errors import EditorError

# How far under the true-peak ceiling the sample-peak limiter holds the peaks, in dB.
LIMIT_MARGIN_DB = 0.5


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


def limit_level(true_peak_db: float) -> float:
    """The sample-peak limit, as a linear level, `LIMIT_MARGIN_DB` under `true_peak_db`."""
    return 10 ** ((true_peak_db - LIMIT_MARGIN_DB) / 20)


def limit_filter(gain_db: float, true_peak_db: float) -> str:
    """The ffmpeg filters that apply `gain_db`, then hold the sample peaks at
    `limit_level(true_peak_db)`, with the limiter's lookahead delay compensated."""
    return (
        f"volume={gain_db:.4f}dB,"
        f"alimiter=limit={limit_level(true_peak_db):.6f}:attack=5:release=50:level=disabled:latency=1"
    )
