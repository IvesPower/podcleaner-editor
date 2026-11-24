import os
import shutil
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from podcleaner_editor.config import Settings
from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.errors import EditorError
from podcleaner_editor.render import writer
from podcleaner_editor.render.splice import fade_curves, splice_plan
from podcleaner_editor.render.writer import (
    RenderTrack,
    check_renderable,
    estimate_bytes,
    write_edit,
)
from podcleaner_editor.timeline import Interval as I

RATE = 1000


def _wav(path, data, rate=RATE, subtype="FLOAT"):
    sf.write(path, np.asarray(data, dtype=np.float32), rate, subtype=subtype)
    return path


def _ramp(n=1000):
    return np.arange(n, dtype=np.float32) / n


def _plan(cuts, n_total=1000, fade_ms=0):
    return splice_plan(CutMap(tuple(I(a, b) for a, b in cuts)), n_total, RATE, fade_ms)


def _settings(fade_ms=0):
    return replace(Settings(), fade_ms=fade_ms)


def _read(path):
    data, _ = sf.read(path, dtype="float32", always_2d=True)
    return data


def test_tracks_cut_at_the_same_samples(tmp_path):
    ramp = _ramp()
    a = _wav(tmp_path / "a.wav", ramp)
    b = _wav(tmp_path / "b.wav", ramp[::-1])
    tracks = [
        RenderTrack(a, tmp_path / "out.a.wav", None),
        RenderTrack(b, tmp_path / "out.b.wav", None),
    ]
    n_out = write_edit(tracks, _plan([(0.4, 0.6)]), 1000, tmp_path / "out.mix.wav", _settings())
    assert n_out == 800
    expected_a = np.concatenate([ramp[0:400], ramp[600:1000]])
    expected_b = np.concatenate([ramp[::-1][0:400], ramp[::-1][600:1000]])
    np.testing.assert_allclose(_read(tmp_path / "out.a.wav")[:, 0], expected_a, atol=1e-7)
    np.testing.assert_allclose(_read(tmp_path / "out.b.wav")[:, 0], expected_b, atol=1e-7)
    assert sf.info(tmp_path / "out.mix.wav").frames == 800


def test_crossfade_at_the_join(tmp_path):
    ramp = _ramp()
    a = _wav(tmp_path / "a.wav", ramp)
    plan = _plan([(0.4, 0.6)], fade_ms=30)
    tracks = [RenderTrack(a, tmp_path / "out.a.wav", None)]
    n_out = write_edit(tracks, plan, 1000, tmp_path / "out.mix.wav", _settings(30))
    assert n_out == 800
    out = _read(tmp_path / "out.a.wav")[:, 0]
    assert len(out) == 800
    rise, fall = fade_curves(15)
    np.testing.assert_allclose(out[385:415], ramp[385:415] * fall + ramp[585:615] * rise, atol=1e-6)
    np.testing.assert_allclose(out[:385], ramp[:385], atol=1e-7)
    np.testing.assert_allclose(out[415:], ramp[615:], atol=1e-7)


def test_crossfade_across_a_block_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "_BLOCK_S", 0.007)
    ramp = _ramp()
    a = _wav(tmp_path / "a.wav", ramp)
    plan = _plan([(0.4, 0.6)], fade_ms=30)
    tracks = [RenderTrack(a, tmp_path / "out.a.wav", (I(0.1, 0.9),))]
    write_edit(tracks, plan, 1000, tmp_path / "out.mix.wav", _settings(30))
    small = _read(tmp_path / "out.a.wav")[:, 0]
    monkeypatch.setattr(writer, "_BLOCK_S", 5.0)
    write_edit(tracks, plan, 1000, tmp_path / "out.mix.wav", _settings(30))
    np.testing.assert_allclose(small, _read(tmp_path / "out.a.wav")[:, 0], atol=1e-7)


def test_mix_is_the_sum(tmp_path):
    voice = _wav(tmp_path / "voice.wav", np.full(1000, 0.5))
    film = _wav(tmp_path / "film.wav", np.full((1000, 2), 0.75))
    tracks = [
        RenderTrack(voice, tmp_path / "out.voice.wav", None),
        RenderTrack(film, tmp_path / "out.film.wav", None),
    ]
    write_edit(tracks, _plan([]), 1000, tmp_path / "out.mix.wav", _settings())
    mix = _read(tmp_path / "out.mix.wav")
    assert mix.shape == (1000, 2)
    np.testing.assert_allclose(mix, 1.25, atol=1e-6)
    info = sf.info(tmp_path / "out.mix.wav")
    assert info.subtype == "FLOAT"
    assert info.format == "WAV"
    assert sf.info(tmp_path / "out.voice.wav").channels == 1
    assert sf.info(tmp_path / "out.film.wav").channels == 2


def test_integer_sources_keep_their_subtype(tmp_path):
    a = _wav(tmp_path / "a.wav", np.full(1000, 0.9), subtype="PCM_24")
    b = _wav(tmp_path / "b.wav", np.full(1000, 0.9), subtype="PCM_24")
    tracks = [
        RenderTrack(a, tmp_path / "out.a.wav", None),
        RenderTrack(b, tmp_path / "out.b.wav", None),
    ]
    write_edit(tracks, _plan([]), 1000, tmp_path / "out.mix.wav", _settings())
    assert sf.info(tmp_path / "out.a.wav").subtype == "PCM_24"
    np.testing.assert_allclose(_read(tmp_path / "out.a.wav"), 0.9, atol=1e-6)
    np.testing.assert_allclose(_read(tmp_path / "out.mix.wav"), 1.8, atol=1e-5)


def test_gate_applied_to_voice_only(tmp_path):
    voice = _wav(tmp_path / "voice.wav", np.full(1000, 0.5))
    film = _wav(tmp_path / "film.wav", np.full(1000, 0.5))
    tracks = [
        RenderTrack(voice, tmp_path / "out.voice.wav", (I(0.2, 0.3),)),
        RenderTrack(film, tmp_path / "out.film.wav", None),
    ]
    write_edit(tracks, _plan([]), 1000, tmp_path / "out.mix.wav", _settings())
    out = _read(tmp_path / "out.voice.wav")[:, 0]
    assert np.all(out[:190] == 0)
    assert np.all(out[401:] == 0)
    np.testing.assert_allclose(out[200:300], 0.5)
    np.testing.assert_allclose(_read(tmp_path / "out.film.wav")[:, 0], 0.5)


def test_shorter_track_sets_the_length(tmp_path):
    a = _wav(tmp_path / "a.wav", _ramp(1000))
    b = _wav(tmp_path / "b.wav", _ramp(1500))
    tracks = [
        RenderTrack(a, tmp_path / "out.a.wav", None),
        RenderTrack(b, tmp_path / "out.b.wav", None),
    ]
    n_out = write_edit(tracks, _plan([(0.4, 0.6)]), 1000, tmp_path / "out.mix.wav", _settings())
    assert n_out == 800
    for name in ("out.a.wav", "out.b.wav", "out.mix.wav"):
        assert sf.info(tmp_path / name).frames == 800


def test_error_mid_write_leaves_no_tmp_and_keeps_old_files(tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "_BLOCK_S", 0.1)
    a = _wav(tmp_path / "a.wav", _ramp())
    targets = [tmp_path / "out.a.wav", tmp_path / "out.mix.wav"]
    for target in targets:
        target.write_text("old", encoding="utf-8")
    real_read = sf.SoundFile.read
    calls = {"n": 0}

    def failing_read(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(sf.SoundFile, "read", failing_read)
    tracks = [RenderTrack(a, targets[0], None)]
    with pytest.raises(KeyboardInterrupt):
        write_edit(tracks, _plan([(0.4, 0.6)]), 1000, targets[1], _settings())
    assert list(tmp_path.glob("*.tmp")) == []
    for target in targets:
        assert target.read_text(encoding="utf-8") == "old"


def test_different_rates_refused(tmp_path):
    a = _wav(tmp_path / "a.wav", np.zeros(100), rate=44100)
    b = _wav(tmp_path / "b.wav", np.zeros(100), rate=48000)
    with pytest.raises(EditorError, match="do not share one sample rate"):
        check_renderable([a, b])
    assert check_renderable([a]) == 44100


def test_more_than_two_channels_refused(tmp_path):
    a = _wav(tmp_path / "a.wav", np.zeros((100, 6)))
    with pytest.raises(EditorError, match="a.wav has 6 channels: only mono or stereo"):
        check_renderable([a])


def test_estimate_counts_tracks_and_stereo_float_mix(tmp_path):
    a = _wav(tmp_path / "a.wav", np.zeros(100), subtype="PCM_16")
    b = _wav(tmp_path / "b.wav", np.zeros((100, 2)), subtype="PCM_24")
    estimate = estimate_bytes([a, b], 1000)
    data = 1000 * 1 * 2 + 1000 * 2 * 3 + 1000 * 2 * 4
    assert data <= estimate <= data + 3 * 4096


def test_large_file_becomes_rf64():
    assert writer._wav_format(0xFFFFFFFF // 8, 2, "DOUBLE") == "RF64"
    assert writer._wav_format(1000, 2, "FLOAT") == "WAV"


def test_not_enough_space(tmp_path, monkeypatch):
    a = _wav(tmp_path / "a.wav", _ramp())
    monkeypatch.setattr(
        shutil, "disk_usage", lambda path: SimpleNamespace(total=100, used=90, free=10)
    )
    tracks = [RenderTrack(a, tmp_path / "out" / "out.a.wav", None)]
    (tmp_path / "out").mkdir()
    with pytest.raises(EditorError, match="Not enough disk space"):
        write_edit(tracks, _plan([]), 1000, tmp_path / "out" / "out.mix.wav", _settings())
    assert os.listdir(tmp_path / "out") == []


@pytest.mark.parametrize("fail_read", [True, False])
def test_close_error_during_cleanup_still_deletes_tmp(tmp_path, monkeypatch, fail_read):
    # fail_read: a read raises, then a close raises during cleanup (the read error wins).
    # Otherwise: the first close of the success path raises, and cleanup still runs.
    monkeypatch.setattr(writer, "_BLOCK_S", 0.1)
    a = _wav(tmp_path / "a.wav", _ramp())
    b = _wav(tmp_path / "b.wav", _ramp())
    targets = [tmp_path / "out.a.wav", tmp_path / "out.b.wav", tmp_path / "out.mix.wav"]
    for target in targets:
        target.write_text("old", encoding="utf-8")
    real_read, real_close = sf.SoundFile.read, sf.SoundFile.close
    calls = {"read": 0, "close": 0}

    def failing_read(self, *args, **kwargs):
        calls["read"] += 1
        if fail_read and calls["read"] == 2:
            raise KeyboardInterrupt
        return real_read(self, *args, **kwargs)

    def failing_close(self):
        # Only the outputs fail, and only once: `sf.info` also closes the sources.
        first = not self.closed and str(self.name).endswith(".tmp") and calls["close"] == 0
        real_close(self)
        if first:
            calls["close"] += 1
            raise OSError("close failed")

    monkeypatch.setattr(sf.SoundFile, "read", failing_read)
    monkeypatch.setattr(sf.SoundFile, "close", failing_close)
    tracks = [RenderTrack(a, targets[0], None), RenderTrack(b, targets[1], None)]
    expected = KeyboardInterrupt if fail_read else OSError
    with pytest.raises(expected):
        write_edit(tracks, _plan([(0.4, 0.6)]), 1000, targets[2], _settings())
    assert calls["close"] >= 1
    assert list(tmp_path.glob("*.tmp")) == []
    for target in targets:
        assert target.read_text(encoding="utf-8") == "old"
