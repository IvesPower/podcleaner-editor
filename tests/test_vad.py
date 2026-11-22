"""Silero on real recordings: samples/pedit/ (local, not in git); skipped when it is absent."""

from pathlib import Path

import numpy as np
import pytest

from podcleaner_editor.analysis.vad import speech_intervals
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k, frame_levels
from podcleaner_editor.config import Settings
from podcleaner_editor.timeline import union

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "pedit"
JULIEN = SAMPLES / "pedit-full-piste-1-julien.wav"
FRANCK = SAMPLES / "pedit-full-piste-2-franck.wav"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not JULIEN.is_file(), reason="samples/pedit/ is not available"),
]


def _speech_share_outside_sound(path: Path) -> float:
    """Share of the detected speech that falls on digital silence (should be ~0)."""
    samples = decode_mono_16k(path)
    speech = speech_intervals(samples, Settings())
    levels = frame_levels(samples, ANALYSIS_RATE, 0.01)
    silent = levels <= -100
    total = sum(i.duration for i in speech)
    on_silence = sum(silent[int(i.start / 0.01) : int(i.end / 0.01)].sum() * 0.01 for i in speech)
    return on_silence / total


def test_speech_found_on_both_voices():
    for path in (JULIEN, FRANCK):
        speech = speech_intervals(decode_mono_16k(path), Settings())
        assert speech, path.name
        assert all(0 <= i.start < i.end <= 75 for i in speech)


def test_speech_is_not_found_on_digital_silence():
    for path in (JULIEN, FRANCK):
        assert _speech_share_outside_sound(path) < 0.1, path.name


def test_julien_talks_most_of_the_first_45_seconds():
    speech = speech_intervals(decode_mono_16k(JULIEN), Settings())
    first = sum(min(i.end, 45) - i.start for i in union(speech) if i.start < 45)
    assert first > 25


def test_silence_gives_no_speech():
    assert speech_intervals(np.zeros(ANALYSIS_RATE * 3, dtype=np.float32), Settings()) == []
