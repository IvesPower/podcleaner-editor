import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from podcleaner_editor.errors import EditorError
from podcleaner_editor.sound import limiter
from podcleaner_editor.sound.limiter import LimiterReport, link_limit

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
    report = link_limit(paths, 0.8, block_s=0.5)
    assert report.passages == 1
    assert 400 / RATE <= report.reduced_s < 600 / RATE
    assert report.deepest_db == pytest.approx(20 * math.log10(0.8 / 1.5), abs=0.05)
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
    report = link_limit([path, _write(tmp_path / "b.wav", a)], 0.8)
    assert path.read_bytes() == before
    assert report == LimiterReport(0, 0.0, 0.0)


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


def test_passages_across_blocks_count_once(tmp_path):
    x = _tone(2 * RATE, 0.3)
    x[1900:2100] *= 3.0  # one passage across the 0.25 s block edge at frame 2000
    x[6000:6100] *= 3.0
    path = _write(tmp_path / "a.wav", x)
    assert link_limit([path], 0.8, block_s=0.25).passages == 2


@pytest.mark.parametrize("step", ["_peaks", "_envelope"])
def test_an_error_leaves_every_file_closed(tmp_path, monkeypatch, step):
    x = _tone(RATE, 0.3)
    x[4000:4100] *= 3.0
    paths = [_write(tmp_path / "a.wav", x), _write(tmp_path / "b.wav", x)]
    opened = []
    real_open = Path.open

    def tracking(self, *args, **kwargs):
        opened.append(real_open(self, *args, **kwargs))
        return opened[-1]

    calls = []
    real_step = getattr(limiter, step)

    def failing(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real_step(*args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking)
    monkeypatch.setattr(limiter, step, failing)
    with pytest.raises(KeyboardInterrupt):
        link_limit(paths, 0.8, gain_db=1.0, block_s=0.25)
    assert opened and all(f.closed for f in opened)
    for path in paths:
        path.rename(path.with_suffix(".moved"))
        path.with_suffix(".moved").unlink()


def test_an_unexpected_temporary_is_an_editor_error(tmp_path):
    path = tmp_path / "a.wav"
    sf.write(path, _tone(RATE, 0.3), RATE, subtype="PCM_16")
    with pytest.raises(EditorError, match="a.wav is not a 32-bit float WAV file"):
        link_limit([path], 0.8)
