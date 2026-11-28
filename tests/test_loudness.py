import numpy as np
import soundfile as sf

from podcleaner_editor.sound.loudness import Loudness, measure, shared_gain


def _sine(path, amplitude=0.1, seconds=10, sr=48000, channels=1):
    t = np.arange(int(seconds * sr)) / sr
    x = (amplitude * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    if channels > 1:
        x = np.stack([x] * channels, axis=1)
    sf.write(path, x, sr, subtype="FLOAT")
    return path


def test_measure_a_sine_at_minus_20_dbfs(tmp_path):
    loud = measure([_sine(tmp_path / "a.wav")])
    assert abs(loud.lufs + 23) < 0.5
    assert abs(loud.true_peak_db + 20) < 0.5


def test_measure_sums_several_files(tmp_path):
    a, b = _sine(tmp_path / "a.wav"), _sine(tmp_path / "b.wav")
    one = measure([a])
    both = measure([a, b])
    assert abs(both.lufs - one.lufs - 6.02) < 0.3
    assert abs(both.true_peak_db - one.true_peak_db - 6.02) < 0.3


def test_measure_sums_mono_and_stereo(tmp_path):
    mono = _sine(tmp_path / "m.wav")
    stereo = _sine(tmp_path / "s.wav", channels=2)
    both = measure([mono, stereo])
    # ffmpeg upmixes mono to stereo at -3 dB: peak 0.1 * 0.707 + 0.1
    assert abs(both.true_peak_db + 15.4) < 0.3
    assert measure([stereo, mono]) == both


def test_measure_silence(tmp_path):
    p = tmp_path / "z.wav"
    sf.write(p, np.zeros(48000 * 2, dtype=np.float32), 48000, subtype="FLOAT")
    loud = measure([p])
    assert loud.lufs == -70.0
    assert loud.true_peak_db == float("-inf")


def test_shared_gain_reaches_the_target():
    assert shared_gain(Loudness(-20, -6), -16, -1) == (4.0, False)


def test_shared_gain_is_lowered_for_the_true_peak():
    assert shared_gain(Loudness(-20, -3), -16, -1) == (2.0, True)


def test_shared_gain_of_silence_is_zero():
    assert shared_gain(Loudness(-70.0, float("-inf")), -16, -1) == (0.0, False)
