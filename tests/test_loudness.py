import numpy as np
import pytest
import soundfile as sf

from podcleaner_editor.sound.loudness import Loudness, film_gain, measure, shared_gain


def _sine(path, amplitude=0.1, seconds=10, sr=48000, channels=1):
    t = np.arange(int(seconds * sr)) / sr
    x = (amplitude * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    if channels > 1:
        x = np.stack([x] * channels, axis=1)
    sf.write(path, x, sr, subtype="FLOAT")
    return path


def test_measure_a_sine_at_minus_20_dbfs(tmp_path):
    loud = measure([_sine(tmp_path / "a.wav")])
    assert abs(loud.lufs + 20) < 0.5  # mono is measured as dual mono, like the mix
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
    assert abs(both.true_peak_db + 14) < 0.2  # full-level mono plus stereo, in phase
    assert measure([stereo, mono]) == both


def test_measure_of_the_mix_equals_the_sum_of_its_tracks(tmp_path):
    from dataclasses import replace

    from podcleaner_editor.config import Settings
    from podcleaner_editor.cutmap import CutMap
    from podcleaner_editor.render.splice import splice_plan
    from podcleaner_editor.render.writer import RenderTrack, write_edit

    sr = 48000
    a = _sine(tmp_path / "a.wav", amplitude=0.1, seconds=5)
    b = _sine(tmp_path / "b.wav", amplitude=0.05, seconds=5)
    film = _sine(tmp_path / "f.wav", amplitude=0.02, seconds=5)
    tracks = [RenderTrack(p, tmp_path / f"out.{p.stem}.wav", None) for p in (a, b, film)]
    plan = splice_plan(CutMap(()), 5 * sr, sr, 0)
    mix = tmp_path / "out.mix.wav"
    write_edit(tracks, plan, 5 * sr, mix, replace(Settings(), fade_ms=0))
    written, summed = measure([mix]), measure([a, b, film])
    assert abs(written.lufs - summed.lufs) < 0.1
    assert abs(written.true_peak_db - summed.true_peak_db) < 0.1


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


def test_measure_applies_a_gain_to_each_input(tmp_path):
    a = _sine(tmp_path / "a.wav")
    plain, lowered = measure([a]), measure([a], gains_db=[-6.0206])
    assert lowered.lufs == pytest.approx(plain.lufs - 6.0206, abs=0.1)
    assert lowered.true_peak_db == pytest.approx(plain.true_peak_db - 6.0206, abs=0.1)


def test_measure_with_gains_matches_the_scaled_sum(tmp_path):
    a = _sine(tmp_path / "a.wav", amplitude=0.1)
    b = _sine(tmp_path / "b.wav", amplitude=0.2)
    halved = _sine(tmp_path / "h.wav", amplitude=0.1)
    assert measure([a, b], gains_db=[0.0, -6.0206]).lufs == pytest.approx(
        measure([a, halved]).lufs, abs=0.1
    )


def test_film_gain_brings_the_film_to_the_voices():
    assert film_gain(Loudness(-20, -6), Loudness(-14, -1)) == pytest.approx(-6.0)


def test_film_gain_is_clamped():
    assert film_gain(Loudness(-20, -6), Loudness(-40, -25)) == 10.0
    assert film_gain(Loudness(-10, -1), Loudness(-5, 0)) == -5.0
    assert film_gain(Loudness(-40, -20), Loudness(-10, -1)) == -20.0


def test_film_gain_of_silence_is_zero():
    silence = Loudness(-70.0, float("-inf"))
    assert film_gain(silence, Loudness(-14, -1)) == 0.0
    assert film_gain(Loudness(-20, -6), silence) == 0.0


def test_film_gain_without_film_clips_is_zero():
    # A noisy film track with no clip found is not raised to the voices.
    assert film_gain(Loudness(-20, -6), Loudness(-40, -25), has_clips=False) == 0.0
