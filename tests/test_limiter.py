import numpy as np
import soundfile as sf

from podcleaner_editor.sound.limiter import link_limit

RATE = 8000


def _write(path, data):
    sf.write(path, np.asarray(data, dtype=np.float32), RATE, subtype="FLOAT")
    return path


def _read(path):
    data, _ = sf.read(path, dtype="float32", always_2d=True)
    return data


def _tone(n, amplitude):
    return amplitude * np.sin(2 * np.pi * 220 * np.arange(n) / RATE)


def test_the_sum_is_held_under_the_limit(tmp_path):
    n = 3 * RATE
    a, b = _tone(n, 0.3), _tone(n, 0.3)
    a[RATE : RATE + 400] *= 2.5  # both peaks together: 1.5 in the sum
    b[RATE : RATE + 400] *= 2.5
    paths = [_write(tmp_path / "a.wav", a), _write(tmp_path / "b.wav", b)]
    link_limit(paths, 0.8, block_s=0.5)
    out_a, out_b = _read(paths[0])[:, 0], _read(paths[1])[:, 0]
    assert np.max(np.abs(out_a + out_b)) <= 0.8 + 1e-6
    # One shared gain: the tracks keep their ratio everywhere.
    np.testing.assert_allclose(out_a, out_b, atol=1e-6)
    # Far from the peak, nothing changes.
    np.testing.assert_allclose(out_a[: RATE - 200], a[: RATE - 200], atol=1e-6)
    np.testing.assert_allclose(out_a[RATE + 600 :], a[RATE + 600 :], atol=1e-6)


def test_mono_and_stereo_are_summed_like_the_mix(tmp_path):
    n = RATE
    mono = _tone(n, 0.5)
    stereo = np.stack([_tone(n, 0.5), np.zeros(n)], axis=1)
    paths = [_write(tmp_path / "m.wav", mono), _write(tmp_path / "s.wav", stereo)]
    link_limit(paths, 0.8, block_s=0.3)
    m, s = _read(paths[0]), _read(paths[1])
    left = m[:, 0] + s[:, 0]
    assert np.max(np.abs(left)) <= 0.8 + 1e-6
    assert np.max(np.abs(m[:, 0] + s[:, 1])) <= 0.8 + 1e-6
    assert s.shape == (n, 2) and m.shape == (n, 1)


def test_quiet_files_are_left_alone(tmp_path):
    a = _tone(RATE, 0.2)
    path = _write(tmp_path / "a.wav", a)
    before = path.read_bytes()
    link_limit([path, _write(tmp_path / "b.wav", a)], 0.8)
    assert path.read_bytes() == before


def test_files_of_different_lengths(tmp_path):
    long, short = _tone(2 * RATE, 0.6), _tone(RATE, 0.6)
    paths = [_write(tmp_path / "l.wav", long), _write(tmp_path / "s.wav", short)]
    link_limit(paths, 0.8, block_s=0.25)
    out_l, out_s = _read(paths[0])[:, 0], _read(paths[1])[:, 0]
    assert len(out_l) == 2 * RATE and len(out_s) == RATE
    assert np.max(np.abs(out_l[:RATE] + out_s)) <= 0.8 + 1e-6
    np.testing.assert_allclose(out_l[RATE + 200 :], long[RATE + 200 :], atol=1e-6)


def test_files_written_by_ffmpeg(tmp_path):
    from podcleaner_editor.sound.filters import apply_filters

    x = _tone(RATE, 0.3)
    x[4000:4100] *= 3.0
    source = _write(tmp_path / "in.wav", x)
    path = tmp_path / "out.wav"
    apply_filters(source, path, "")  # its header holds more than libsndfile writes
    link_limit([path], 0.8)
    out = _read(path)[:, 0]
    assert len(out) == RATE and np.all(np.isfinite(out))
    assert np.max(np.abs(out)) <= 0.8 + 1e-6
    np.testing.assert_allclose(out[:3800], x[:3800], atol=1e-6)


def test_a_gain_is_applied_before_limiting(tmp_path):
    x = _tone(RATE, 0.2)
    x[4000:4100] *= 3.0  # 0.6, past 0.8 once doubled
    path = _write(tmp_path / "a.wav", x)
    link_limit([path], 0.8, gain_db=6.0206)
    out = _read(path)[:, 0]
    assert np.max(np.abs(out)) <= 0.8 + 1e-6
    np.testing.assert_allclose(out[:3800], 2 * x[:3800], atol=1e-5)
    np.testing.assert_allclose(out[4300:], 2 * x[4300:], atol=1e-5)
