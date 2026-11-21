import numpy as np
import pytest

from podcleaner_editor import audio_io
from podcleaner_editor.audio_io import decode_mono_16k, frame_levels, probe, require_ffmpeg
from podcleaner_editor.errors import EditorError


def test_decode_returns_mono_16k_float32(make_wav, tmp_path):
    p = make_wav(tmp_path / "a.wav", seconds=2, sr=48000, channels=2)
    x = decode_mono_16k(p)
    assert x.dtype == np.float32 and x.ndim == 1 and abs(len(x) - 32000) <= 160


def test_decode_keeps_the_signal_level(make_wav, tmp_path):
    p = make_wav(tmp_path / "tone.wav", seconds=1, signal="tone")
    x = decode_mono_16k(p)
    assert abs(float(np.max(np.abs(x))) - 0.5) < 0.02


def test_probe_reads_duration_rate_and_channels(make_wav, tmp_path):
    p = make_wav(tmp_path / "a.wav", seconds=3, sr=44100, channels=2, subtype="FLOAT")
    info = probe(p)
    assert abs(info.duration - 3) < 0.01
    assert (info.sample_rate, info.channels) == (44100, 2)
    assert info.codec.startswith("pcm_")


def test_frame_levels_of_full_scale_sine_is_about_minus_3_dbfs():
    sr = 16000
    x = np.sin(2 * np.pi * 1000 * np.arange(sr) / sr).astype(np.float32)
    levels = frame_levels(x, sr, 0.01)
    assert len(levels) == 100
    assert np.all(np.abs(levels + 3.01) < 0.5)


def test_frame_levels_of_silence_is_floor():
    levels = frame_levels(np.zeros(1600, dtype=np.float32), 16000, 0.01)
    assert np.all(levels == -120.0)


def test_frame_levels_keeps_a_last_partial_frame():
    assert len(frame_levels(np.zeros(1650, dtype=np.float32), 16000, 0.01)) == 11


def test_require_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(audio_io.shutil, "which", lambda name: None)
    with pytest.raises(EditorError, match="ffmpeg") as exc:
        require_ffmpeg()
    assert "install" in str(exc.value).lower()
