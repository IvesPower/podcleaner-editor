"""Removing noise and reverb from a voice track, slice by slice."""

import math
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import soundfile as sf

from podcleaner_editor.errors import EditorError

# Length of the linear crossfade in the middle of each overlap.
_CROSSFADE_S = 0.5
# Extra audio read on each side of a slice, so resampling leaves no edge artefacts.
_MARGIN_S = 0.1
# Kaiser window of the resampling filter: flatter passband than scipy's default 5.0.
_WINDOW = ("kaiser", 8.0)


class Denoiser(Protocol):
    """Cleans a mono float32 signal at `rate`, returning as many samples."""

    name: str
    rate: int

    def __call__(self, mono: np.ndarray) -> np.ndarray: ...


class _DeepFilterNet:
    """DeepFilterNet 3, loaded on the first call."""

    name = "DeepFilterNet 3"
    rate = 48000

    def __init__(self) -> None:
        self._model: Any = None
        self._state: Any = None
        self._enhance: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        try:
            from df.enhance import enhance, init_df  # imported late: loading it is slow

            model, state, _ = init_df(log_level="ERROR", log_file=None)
            import torch  # already loaded by df
        except Exception as exc:
            raise EditorError(f"Could not load the DeepFilterNet model: {exc}") from exc
        self._model, self._state = model, state
        self._enhance, self._torch = enhance, torch

    def __call__(self, mono: np.ndarray) -> np.ndarray:
        if self._model is None:
            self._load()
        audio = self._torch.from_numpy(np.ascontiguousarray(mono, dtype=np.float32))[None]
        out = self._enhance(self._model, self._state, audio).numpy()[0]
        return out.astype(np.float32, copy=False)


def make_denoiser() -> Denoiser:
    """DeepFilterNet 3 at 48 kHz; the model is loaded (and downloaded) on first use."""
    return _DeepFilterNet()


def _resample(x: np.ndarray, up: int, down: int) -> np.ndarray:
    if up == down:
        return x
    from scipy.signal import resample_poly  # imported late: loading it is slow

    return resample_poly(x, up, down, window=_WINDOW).astype(np.float32, copy=False)


def _process(
    raw: sf.SoundFile, start: int, end: int, denoiser: Denoiser, up: int, down: int
) -> np.ndarray:
    """The denoised mono `[start, end)` at the source rate, read with a margin and trimmed."""
    margin = round(_MARGIN_S * raw.samplerate)
    lo = max(start - margin, 0)
    hi = min(end + margin, raw.frames)
    raw.seek(lo)
    mono = raw.read(hi - lo, dtype="float32", always_2d=True).mean(axis=1, dtype=np.float32)
    clean = np.asarray(denoiser(_resample(mono, up, down)), dtype=np.float32)
    back = _resample(clean, down, up)
    piece = back[start - lo : end - lo]
    if len(piece) < end - start:
        piece = np.pad(piece, (0, end - start - len(piece)))
    return piece


def denoise_file(
    source: Path,
    target: Path,
    denoiser: Denoiser,
    *,
    slice_s: float = 30.0,
    overlap_s: float = 1.0,
) -> None:
    """Writes `source` denoised to `target`: FLOAT, same rate, channels and length.

    The mono average is cleaned in slices of `slice_s` that overlap by `overlap_s`,
    joined by a linear crossfade over the middle of each overlap.
    """
    with sf.SoundFile(source) as raw:
        sr, channels, n = raw.samplerate, raw.channels, raw.frames
        ratio = math.gcd(denoiser.rate, sr)
        up, down = denoiser.rate // ratio, sr // ratio
        length = max(round(slice_s * sr), 1)
        overlap = min(max(round(overlap_s * sr), 0), length - 1)
        hop = length - overlap
        fade = min(round(_CROSSFADE_S * sr), overlap)
        fade_at = (overlap - fade) // 2
        ramp = ((np.arange(fade) + 0.5) / fade).astype(np.float32) if fade else None
        with sf.SoundFile(
            target, "w", samplerate=sr, channels=channels, subtype="FLOAT", format="WAV"
        ) as out:
            start = 0
            pending: np.ndarray | None = None
            while start < n:
                end = min(start + length, n)
                piece = _process(raw, start, end, denoiser, up, down)
                if pending is not None:
                    # The previous slice's output from this slice's `start + fade_at`.
                    piece = piece[fade_at:]
                    if ramp is not None:
                        piece[:fade] = pending * (1 - ramp) + piece[:fade] * ramp
                    offset = start + fade_at
                else:
                    offset = start
                if end == n:
                    keep, pending = piece, None
                else:
                    split = start + hop + fade_at - offset
                    keep, pending = piece[:split], piece[split : split + fade]
                out.write(np.repeat(keep[:, None], channels, axis=1))
                if end == n:
                    break
                start += hop
