"""Reading audio with ffprobe/ffmpeg: file facts, a 16 kHz mono copy for analysis, levels."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from podcleaner_editor.errors import EditorError

ANALYSIS_RATE = 16000
LEVEL_FLOOR_DB = -120.0
_BLOCK_SAMPLES = 16000 * 60  # one minute at the analysis rate


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration: float
    sample_rate: int
    channels: int
    codec: str
    container: str = ""  # ffprobe format name, "wav" for a WAV file


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise EditorError(
            "ffmpeg not found. Install it (macOS: brew install ffmpeg; "
            "Windows: winget install ffmpeg) and run again."
        )


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, check=False)
    except OSError as exc:
        raise EditorError(f"Could not run {args[0]}: {exc}") from exc


def probe(path: Path) -> AudioInfo:
    """Duration, sample rate, channels and codec of the first audio stream of `path`."""
    path = Path(path)
    if not path.is_file():
        raise EditorError(f"File not found: {path}")
    done = _run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    )
    if done.returncode != 0:
        message = done.stderr.decode("utf-8", errors="replace").strip()
        raise EditorError(f"Cannot read {path}: {message or 'ffprobe failed'}")
    data = json.loads(done.stdout.decode("utf-8", errors="replace"))
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if stream is None:
        raise EditorError(f"No audio in {path}")
    duration = stream.get("duration") or data.get("format", {}).get("duration") or 0
    return AudioInfo(
        path=path,
        duration=float(duration),
        sample_rate=int(stream.get("sample_rate", 0)),
        channels=int(stream.get("channels", 0)),
        codec=str(stream.get("codec_name", "")),
        container=str(data.get("format", {}).get("format_name", "")),
    )


def decode_mono_16k(path: Path) -> np.ndarray:
    """The whole file as float32 samples, mono (channel average), at 16 kHz."""
    done = _run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path]
        + ["-ac", "1", "-ar", str(ANALYSIS_RATE), "-f", "f32le", "-"]
    )
    if done.returncode != 0:
        message = done.stderr.decode("utf-8", errors="replace").strip()
        raise EditorError(f"Cannot decode {path}: {message or 'ffmpeg failed'}")
    return np.frombuffer(done.stdout, dtype="<f4").astype(np.float32, copy=False)


def frame_levels(samples: np.ndarray, sr: int, hop_s: float) -> np.ndarray:
    """RMS level in dBFS of each `hop_s` frame (a last partial frame included), floor -120."""
    hop = max(1, int(round(hop_s * sr)))
    full = len(samples) // hop
    mean_square = np.empty(full + (1 if len(samples) % hop else 0), dtype=np.float64)
    # Blocks of frames: a 2 h track is never copied whole into float64.
    block = max(1, _BLOCK_SAMPLES // hop)
    for first in range(0, full, block):
        last = min(full, first + block)
        frames = samples[first * hop : last * hop].astype(np.float64).reshape(-1, hop)
        mean_square[first:last] = np.mean(frames**2, axis=1)
    if len(mean_square) > full:  # a last partial frame, averaged over its real length
        tail = samples[full * hop :].astype(np.float64)
        mean_square[full] = np.mean(tail**2)
    floor = 10 ** (LEVEL_FLOOR_DB / 20)
    return 20 * np.log10(np.maximum(np.sqrt(mean_square), floor))
