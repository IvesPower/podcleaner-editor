import builtins
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import butter, sosfilt

from podcleaner_editor.errors import EditorError
from podcleaner_editor.sound.denoise import denoise_file, make_denoiser

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "pedit"


class _Fake:
    """A denoiser that scales its input and records the lengths it receives."""

    name = "fake"

    def __init__(self, rate: int = 48000, scale: float = 1.0) -> None:
        self.rate = rate
        self.scale = scale
        self.lengths: list[int] = []

    def __call__(self, mono: np.ndarray) -> np.ndarray:
        assert mono.dtype == np.float32
        self.lengths.append(len(mono))
        return (mono * self.scale).astype(np.float32)


def _band_limited_noise(n: int, sr: int, channels: int, seed: int = 0) -> np.ndarray:
    """Noise below 16 kHz, faded in and out over 10 ms, like any real recording's edges."""
    rng = np.random.default_rng(seed)
    sos = butter(8, 16000, fs=sr, output="sos")
    data = sosfilt(sos, rng.uniform(-0.5, 0.5, (n, channels)), axis=0)
    ramp = np.linspace(0.0, 1.0, int(0.01 * sr))
    data[: len(ramp)] *= ramp[:, None]
    data[-len(ramp) :] *= ramp[::-1, None]
    return data.astype(np.float32)


def test_identity_denoiser_keeps_the_audio(tmp_path):
    sr = 44100
    data = _band_limited_noise(70 * sr, sr, 2)
    source = tmp_path / "in.wav"
    target = tmp_path / "out.wav"
    sf.write(source, data, sr, subtype="FLOAT")

    denoise_file(source, target, _Fake())

    out, out_sr = sf.read(target, dtype="float32", always_2d=True)
    assert out_sr == sr
    assert sf.info(target).subtype == "FLOAT"
    assert out.shape == data.shape
    mono = data.mean(axis=1)
    assert np.abs(out[:, 0] - mono).max() < 1e-3
    assert np.array_equal(out[:, 0], out[:, 1])


def test_slices_join_without_a_dip(tmp_path):
    sr = 44100
    n = 70 * sr
    tone = (0.5 * np.sin(2 * np.pi * 1000 * np.arange(n) / sr)).astype(np.float32)
    source = tmp_path / "in.wav"
    target = tmp_path / "out.wav"
    sf.write(source, tone, sr, subtype="FLOAT")

    denoise_file(source, target, _Fake(scale=0.5))

    out, _ = sf.read(target, dtype="float64")
    assert out.shape == (n,)
    frame = int(0.01 * sr)
    frames = out[: n - n % frame].reshape(-1, frame)
    rms_db = 20 * np.log10(np.sqrt(np.mean(frames**2, axis=1)))
    assert np.abs(rms_db - np.median(rms_db)).max() < 0.2
    assert np.median(rms_db) == pytest.approx(20 * np.log10(0.25 / np.sqrt(2)), abs=0.05)


def test_denoiser_sees_its_own_rate(tmp_path):
    sr = 44100
    source = tmp_path / "in.wav"
    sf.write(source, np.zeros(10 * sr, dtype=np.float32), sr, subtype="FLOAT")
    fake = _Fake(rate=48000)

    denoise_file(source, tmp_path / "out.wav", fake)

    # One slice, no margin past the file's edges: exactly 10 s at 48 kHz.
    assert fake.lengths == [10 * 48000]

    long_source = tmp_path / "long.wav"
    sf.write(long_source, np.zeros(70 * sr, dtype=np.float32), sr, subtype="FLOAT")
    fake = _Fake(rate=48000)

    denoise_file(long_source, tmp_path / "long-out.wav", fake)

    # Three slices: 70 s plus two 1 s overlaps, plus small margins for the resampling.
    assert len(fake.lengths) == 3
    assert 72 * 48000 <= sum(fake.lengths) <= 72.5 * 48000


def test_model_load_failure_is_an_editor_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "df" or name.startswith("df."):
            raise OSError("offline")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    denoiser = make_denoiser()
    assert denoiser.name == "DeepFilterNet 3"
    assert denoiser.rate == 48000

    with pytest.raises(EditorError) as info:
        denoiser(np.zeros(48000, dtype=np.float32))
    assert str(info.value) == "Could not load the DeepFilterNet model: offline"


def test_broken_model_cache_is_an_editor_error(monkeypatch):
    def init_df(**kwargs):
        raise SystemExit(1)

    enhance = types.ModuleType("df.enhance")
    enhance.init_df = init_df
    enhance.enhance = None
    monkeypatch.setitem(sys.modules, "df", types.ModuleType("df"))
    monkeypatch.setitem(sys.modules, "df.enhance", enhance)

    with pytest.raises(EditorError) as info:
        make_denoiser()(np.zeros(48000, dtype=np.float32))
    assert str(info.value) == (
        "Could not load the DeepFilterNet model: no checkpoint found in its cache"
    )


def test_model_error_is_an_editor_error(monkeypatch):
    def enhance(model, state, audio):
        raise RuntimeError("out of memory")

    module = types.ModuleType("df.enhance")
    module.init_df = lambda **kwargs: (object(), object(), "")
    module.enhance = enhance
    monkeypatch.setitem(sys.modules, "df", types.ModuleType("df"))
    monkeypatch.setitem(sys.modules, "df.enhance", module)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(from_numpy=lambda a: a))

    with pytest.raises(EditorError) as info:
        make_denoiser()(np.zeros(48000, dtype=np.float32))
    assert str(info.value) == "DeepFilterNet failed: out of memory"


class _PerCallOffset:
    """A denoiser that adds a tenth of its call number, so each slice is recognisable."""

    name = "offset"
    rate = 48000

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, mono: np.ndarray) -> np.ndarray:
        self.calls += 1
        return (mono + 0.1 * self.calls).astype(np.float32)


def test_slices_land_at_their_place(tmp_path):
    sr = 44100
    n = 70 * sr
    data = _band_limited_noise(n, sr, 1)[:, 0]
    source = tmp_path / "in.wav"
    target = tmp_path / "out.wav"
    sf.write(source, data, sr, subtype="FLOAT")

    denoise_file(source, target, _PerCallOffset())

    out, _ = sf.read(target, dtype="float64")
    # Slices start every 29 s; the 0.5 s crossfade starts 0.25 s into each 1 s overlap.
    # A slice shifted by one frame breaks the noise; a misplaced crossfade breaks the offsets.
    hop, fade_at, fade = 29 * sr, sr // 4, sr // 2
    offset = np.full(n, 0.1)
    for k in (1, 2):
        start = k * hop + fade_at
        ramp = (np.arange(fade) + 0.5) / fade
        offset[start : start + fade] = 0.1 * (k + ramp)
        offset[start + fade :] = 0.1 * (k + 1)
    # The offset steps at the file's own edges, where the resampling rings.
    edge = 200
    error = np.abs(out - (data + offset))[edge:-edge]
    assert out.shape == (n,)
    assert error.max() < 1e-3


def _floor_db(x: np.ndarray, sr: int) -> float:
    """The noise floor: the 10th percentile of the 50 ms frame levels."""
    frame = int(0.05 * sr)
    frames = x[: len(x) - len(x) % frame].reshape(-1, frame)
    return float(np.percentile(20 * np.log10(np.sqrt(np.mean(frames**2, axis=1)) + 1e-12), 10))


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_deepfilternet_lowers_noise(tmp_path):
    with sf.SoundFile(SAMPLES / "pedit-full-piste-1-julien.wav") as raw:
        sr = raw.samplerate
        speech = raw.read(40 * sr, dtype="float32", always_2d=True).mean(axis=1)
    t = np.arange(len(speech)) / sr
    rng = np.random.default_rng(0)
    noisy = speech + 0.01 * rng.standard_normal(len(speech)) + 0.01 * np.sin(2 * np.pi * 60 * t)
    source = tmp_path / "noisy.wav"
    target = tmp_path / "clean.wav"
    sf.write(source, noisy.astype(np.float32), sr, subtype="FLOAT")

    denoise_file(source, target, make_denoiser())

    out, out_sr = sf.read(target, dtype="float32")
    assert out_sr == sr
    assert out.shape == noisy.shape
    assert _floor_db(out, sr) < _floor_db(noisy, sr) - 10
