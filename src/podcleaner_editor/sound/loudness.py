"""Loudness (EBU R128 with true peak) of tracks and their sum, the film gain and the shared
gain."""

import math
import re
from dataclasses import dataclass
from pathlib import Path

from podcleaner_editor.audio_io import _run, probe
from podcleaner_editor.errors import EditorError

SILENCE_LUFS = -70.0
# Range of the gain that brings the film to the voices.
FILM_GAIN_MIN_DB = -20.0
FILM_GAIN_MAX_DB = 10.0
_INTEGRATED = re.compile(r"^\s*I:\s*(-?inf|-?[\d.]+)\s*LUFS", re.MULTILINE)
_PEAK = re.compile(r"True peak:.*?^\s*Peak:\s*(-?inf|-?[\d.]+)\s*dBFS", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True)
class Loudness:
    lufs: float
    true_peak_db: float


def measure(paths: list[Path], gains_db: list[float] | None = None) -> Loudness:
    """Integrated loudness and true peak of one file, or of the sum of several, each input
    first multiplied by its gain in `gains_db` (default: all 0 dB).

    Measured as the mix is written: the writer copies a mono track to both channels at
    full level, so every input is brought to stereo that way (mono: `pan=stereo|c0=c0|c1=c0`)
    before summing; the measure is always taken on that stereo result, even for one mono file.
    """
    if not paths:
        raise EditorError("Nothing to measure.")
    gains_db = [0.0] * len(paths) if gains_db is None else gains_db
    if len(gains_db) != len(paths):
        raise ValueError(f"{len(gains_db)} gains for {len(paths)} files.")
    args = ["ffmpeg", "-nostdin", "-nostats", "-hide_banner"]
    for path in paths:
        args += ["-i", path]
    prep = ""
    for i, (path, gain) in enumerate(zip(paths, gains_db, strict=True)):
        volume = f"volume={gain}dB," if gain != 0.0 else ""
        if probe(path).channels == 1:
            prep += f"[{i}:a]{volume}pan=stereo|c0=c0|c1=c0[c{i}];"
        else:
            prep += f"[{i}:a]{volume}anull[c{i}];"
    inputs = "".join(f"[c{i}]" for i in range(len(paths)))
    if len(paths) > 1:
        chain = f"{prep}{inputs}amix=inputs={len(paths)}:normalize=0,ebur128=peak=true[out]"
    else:
        chain = f"{prep}[c0]ebur128=peak=true[out]"
    args += ["-filter_complex", chain, "-map", "[out]", "-f", "null", "-"]
    done = _run(args)
    text = done.stderr.decode("utf-8", errors="replace")
    summary = text[text.rfind("Summary:") :] if "Summary:" in text else ""
    integrated = _INTEGRATED.search(summary)
    peak = _PEAK.search(summary)
    if done.returncode != 0 or integrated is None or peak is None:
        raise EditorError(f"ffmpeg could not measure the loudness: {text.strip()[-500:]}")
    lufs = float(integrated.group(1))
    if lufs <= SILENCE_LUFS:
        lufs = SILENCE_LUFS
    return Loudness(lufs=lufs, true_peak_db=float(peak.group(1)))


def shared_gain(loudness: Loudness, target_lufs: float, true_peak_db: float) -> tuple[float, bool]:
    """The gain in dB that brings the sum to `target_lufs`, and whether the true peak limited it."""
    if loudness.lufs <= SILENCE_LUFS:
        return 0.0, False
    gain = target_lufs - loudness.lufs
    if not math.isinf(loudness.true_peak_db) and loudness.true_peak_db + gain > true_peak_db:
        return true_peak_db - loudness.true_peak_db, True
    return gain, False


def film_gain(voices: Loudness, film: Loudness) -> float:
    """The gain in dB that brings the film to the voices' loudness, within
    [`FILM_GAIN_MIN_DB`, `FILM_GAIN_MAX_DB`]; 0 when either is silence."""
    if voices.lufs <= SILENCE_LUFS or film.lufs <= SILENCE_LUFS:
        return 0.0
    return min(max(voices.lufs - film.lufs, FILM_GAIN_MIN_DB), FILM_GAIN_MAX_DB)
