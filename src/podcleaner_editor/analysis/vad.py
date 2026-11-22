"""Speech detection with Silero VAD (ONNX model shipped with the silero-vad package)."""

from functools import cache
from typing import Any

import numpy as np

from podcleaner_editor.audio_io import ANALYSIS_RATE
from podcleaner_editor.config import Settings
from podcleaner_editor.timeline import Interval


@cache
def _model() -> Any:
    from silero_vad import load_silero_vad  # imported here: loading torch takes a moment

    return load_silero_vad(onnx=True)


def speech_intervals(samples: np.ndarray, settings: Settings) -> list[Interval]:
    """Where `samples` (16 kHz mono float32) holds speech, in seconds."""
    import torch
    from silero_vad import get_speech_timestamps

    if samples.size == 0:
        return []
    # A copy: decoded samples are a read-only view of ffmpeg's output, torch wants it writable.
    audio = torch.from_numpy(np.array(samples, dtype=np.float32, copy=True))
    stamps = get_speech_timestamps(
        audio,
        _model(),
        threshold=settings.vad_threshold,
        sampling_rate=ANALYSIS_RATE,
        min_speech_duration_ms=settings.vad_min_speech_ms,
        min_silence_duration_ms=settings.vad_min_silence_ms,
        return_seconds=True,
    )
    return [Interval(float(s["start"]), float(s["end"])) for s in stamps]
