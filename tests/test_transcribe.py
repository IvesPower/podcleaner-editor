import sys
import types
from pathlib import Path

import numpy as np
import pytest

from podcleaner_editor.analysis import transcribe
from podcleaner_editor.analysis.transcribe import make_transcriber, transcribe_passages
from podcleaner_editor.analysis.words import Word
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k
from podcleaner_editor.config import Settings
from podcleaner_editor.errors import EditorError
from podcleaner_editor.timeline import Interval as I

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "pedit"
JULIEN = SAMPLES / "pedit-full-piste-1-julien.wav"


class FakeTranscriber:
    name = "fake"

    def __init__(self):
        self.calls = []

    def words(self, audio, offset):
        self.calls.append((len(audio), offset))
        return [Word("b", offset + 0.5, offset + 0.7), Word("a", offset + 0.1, offset + 0.3)]


def test_transcribe_passages_shifts_times():
    fake = FakeTranscriber()
    samples = np.zeros(20 * ANALYSIS_RATE, dtype=np.float32)
    words = transcribe_passages(samples, [I(10.0, 12.0), I(3.0, 4.0)], fake)
    assert fake.calls == [(2 * ANALYSIS_RATE, 10.0), (ANALYSIS_RATE, 3.0)]
    assert [(w.text, w.start) for w in words] == [("a", 3.1), ("b", 3.5), ("a", 10.1), ("b", 10.5)]


def _use_backend(monkeypatch, darwin: bool):
    monkeypatch.setattr(transcribe.sys, "platform", "darwin" if darwin else "linux")
    monkeypatch.setattr(transcribe.platform, "machine", lambda: "arm64" if darwin else "x86_64")


def test_mlx_backend_passes_prompt_and_language(monkeypatch):
    seen = {}

    def fake_transcribe(audio, **kwargs):
        seen.update(kwargs)
        return {"segments": [{"words": [{"word": " Bonjour", "start": 0.1, "end": 0.4}]}]}

    monkeypatch.setitem(
        sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=fake_transcribe)
    )
    _use_backend(monkeypatch, darwin=True)
    settings = Settings()
    transcriber = make_transcriber(settings)
    words = transcriber.words(np.zeros(16000), offset=2.0)
    assert transcriber.name == "mlx-whisper large-v3-turbo"
    assert words == [Word("Bonjour", 2.1, 2.4)]
    assert seen["initial_prompt"] == settings.transcription_prompt
    assert seen["language"] == "fr"
    assert seen["word_timestamps"] is True
    assert seen["condition_on_previous_text"] is False
    assert seen["path_or_hf_repo"] == "mlx-community/whisper-large-v3-turbo"


def test_faster_whisper_backend_passes_prompt_and_language(monkeypatch):
    seen = {}

    class FakeModel:
        def __init__(self, name, compute_type):
            seen["model"] = (name, compute_type)

        def transcribe(self, audio, **kwargs):
            seen.update(kwargs)
            word = types.SimpleNamespace(word=" salut", start=0.2, end=0.5)
            return [types.SimpleNamespace(words=[word])], None

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )
    _use_backend(monkeypatch, darwin=False)
    settings = Settings()
    transcriber = make_transcriber(settings)
    words = transcriber.words(np.zeros(16000), offset=1.0)
    assert transcriber.name == "faster-whisper large-v3-turbo"
    assert words == [Word("salut", 1.2, 1.5)]
    assert seen["model"] == ("large-v3-turbo", "int8")
    assert seen["initial_prompt"] == settings.transcription_prompt
    assert seen["language"] == "fr"
    assert seen["word_timestamps"] is True
    assert seen["condition_on_previous_text"] is False


def test_model_load_failure_is_an_editor_error(monkeypatch):
    def failing(audio, **kwargs):
        raise OSError("offline")

    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=failing))
    _use_backend(monkeypatch, darwin=True)
    with pytest.raises(EditorError) as info:
        make_transcriber(Settings()).words(np.zeros(16000), offset=0.0)
    assert str(info.value) == "Could not load the Whisper model large-v3-turbo: offline"


def test_faster_whisper_load_failure_is_an_editor_error(monkeypatch):
    def failing(name, compute_type):
        raise OSError("offline")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=failing))
    _use_backend(monkeypatch, darwin=False)
    with pytest.raises(
        EditorError, match="Could not load the Whisper model large-v3-turbo: offline"
    ):
        make_transcriber(Settings()).words(np.zeros(16000), offset=0.0)


def test_mlx_failure_after_the_first_call_is_an_editor_error(monkeypatch):
    calls = []

    def flaky(audio, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("out of memory")
        return {"segments": []}

    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=flaky))
    _use_backend(monkeypatch, darwin=True)
    transcriber = make_transcriber(Settings())
    assert transcriber.words(np.zeros(16000), offset=0.0) == []
    with pytest.raises(EditorError) as info:
        transcriber.words(np.zeros(16000), offset=0.0)
    assert str(info.value) == "Could not transcribe with mlx-whisper large-v3-turbo: out of memory"


def _fake_faster_whisper(monkeypatch, segments, seen=None):
    class FakeModel:
        def __init__(self, name, compute_type, **kwargs):
            if seen is not None:
                seen.append(kwargs.get("device", "auto"))

        def transcribe(self, audio, **kwargs):
            return segments(self), None

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )
    _use_backend(monkeypatch, darwin=False)


def test_faster_whisper_lazy_failure_is_an_editor_error(monkeypatch):
    def segments(model):
        yield types.SimpleNamespace(words=[types.SimpleNamespace(word=" a", start=0, end=1)])
        raise RuntimeError("decoder broke")

    _fake_faster_whisper(monkeypatch, segments)
    with pytest.raises(EditorError) as info:
        make_transcriber(Settings()).words(np.zeros(16000), offset=0.0)
    assert str(info.value) == (
        "Could not transcribe with faster-whisper large-v3-turbo: decoder broke"
    )


def test_faster_whisper_gpu_failure_retries_on_cpu(monkeypatch):
    devices = []

    def segments(model):
        if devices[-1] != "cpu":
            raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")
        yield types.SimpleNamespace(words=[types.SimpleNamespace(word=" salut", start=0, end=1)])

    _fake_faster_whisper(monkeypatch, segments, devices)
    transcriber = make_transcriber(Settings())
    assert transcriber.words(np.zeros(16000), offset=0.0) == [Word("salut", 0.0, 1.0)]
    assert devices == ["auto", "cpu"]
    assert transcriber.words(np.zeros(16000), offset=0.0) == [Word("salut", 0.0, 1.0)]
    assert devices == ["auto", "cpu"]  # the model is loaded once on the cpu


def test_faster_whisper_gpu_load_failure_retries_on_cpu(monkeypatch):
    devices = []

    class FakeModel:
        def __init__(self, name, compute_type, **kwargs):
            devices.append(kwargs.get("device", "auto"))
            if kwargs.get("device") != "cpu":
                raise RuntimeError("CUDA failed with error CUDA driver version is insufficient")

        def transcribe(self, audio, **kwargs):
            return [], None

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )
    _use_backend(monkeypatch, darwin=False)
    assert make_transcriber(Settings()).words(np.zeros(16000), offset=0.0) == []
    assert devices == ["auto", "cpu"]


def test_faster_whisper_other_failure_is_not_retried(monkeypatch):
    devices = []

    def segments(model):
        raise RuntimeError("decoder broke")
        yield

    _fake_faster_whisper(monkeypatch, segments, devices)
    with pytest.raises(EditorError, match="Could not transcribe with faster-whisper"):
        make_transcriber(Settings()).words(np.zeros(16000), offset=0.0)
    assert devices == ["auto"]


@pytest.mark.slow
@pytest.mark.skipif(not JULIEN.is_file(), reason="samples/pedit/ is not available")
def test_transcribes_french_speech():
    samples = decode_mono_16k(JULIEN)[: 15 * ANALYSIS_RATE]
    words = transcribe_passages(samples, [I(0.0, 15.0)], make_transcriber(Settings()))
    assert len(words) >= 10
    assert all(0 <= w.start <= w.end <= 15 for w in words)
