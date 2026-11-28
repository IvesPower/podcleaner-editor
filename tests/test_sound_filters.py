import numpy as np
import pytest
import soundfile as sf

from podcleaner_editor.errors import EditorError
from podcleaner_editor.sound.filters import apply_filters


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
