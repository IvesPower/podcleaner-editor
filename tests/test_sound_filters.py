import numpy as np
import pytest
import soundfile as sf

from podcleaner_editor.errors import EditorError
from podcleaner_editor.sound.filters import apply_filters, limit_filter


def _source(tmp_path, channels=2, sr=44100):
    x = np.full((sr, channels), 0.4, dtype=np.float32)
    sf.write(tmp_path / "in.wav", x, sr, subtype="PCM_16")
    return tmp_path / "in.wav"


def test_volume_filter_halves_the_amplitude(tmp_path):
    src = _source(tmp_path)
    apply_filters(src, tmp_path / "out.wav", "volume=-6dB")
    y, sr = sf.read(tmp_path / "out.wav", dtype="float32")
    assert sf.info(tmp_path / "out.wav").subtype == "FLOAT"
    assert sr == 44100 and y.shape[1] == 2
    assert abs(float(np.max(np.abs(y))) - 0.4 * 0.5012) < 0.005


def test_empty_filters_copy_the_audio(tmp_path):
    src = _source(tmp_path, channels=1, sr=32000)
    apply_filters(src, tmp_path / "out.wav", "")
    x, _ = sf.read(src, dtype="float32")
    y, sr = sf.read(tmp_path / "out.wav", dtype="float32")
    assert sf.info(tmp_path / "out.wav").subtype == "FLOAT"
    assert sr == 32000 and y.shape == x.shape
    assert np.allclose(x, y, atol=1e-6)


def test_a_bad_filter_raises(tmp_path):
    with pytest.raises(EditorError, match="could not apply the sound filters"):
        apply_filters(_source(tmp_path), tmp_path / "out.wav", "nosuchfilter=1")


def test_limit_filter_string():
    assert limit_filter(3.5, -1.0) == (
        "volume=3.5000dB,alimiter=limit=0.841395:attack=5:release=50:level=disabled:latency=1"
    )


def test_limit_filter_holds_the_peaks_and_keeps_the_timing(tmp_path):
    sr = 48000
    x = np.zeros(sr, dtype=np.float32)
    x[10000] = 0.5  # +6 dB would take it to 1.0
    x[20000:30000] = 0.05 * np.sin(2 * np.pi * 440 * np.arange(10000) / sr)
    sf.write(tmp_path / "in.wav", x, sr, subtype="FLOAT")
    apply_filters(tmp_path / "in.wav", tmp_path / "out.wav", limit_filter(6.0206, -1.0))
    y, _ = sf.read(tmp_path / "out.wav", dtype="float32")
    assert len(y) == len(x)
    assert int(np.argmax(np.abs(y))) == 10000  # no lookahead delay
    assert float(np.max(np.abs(y))) <= 10 ** (-1.5 / 20) + 1e-3
    # Quiet passages only get the gain.
    np.testing.assert_allclose(y[25000:29000], 2 * x[25000:29000], atol=2e-3)
