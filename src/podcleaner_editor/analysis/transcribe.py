"""Word-level transcription of speech passages: mlx-whisper on Apple silicon, faster-whisper
elsewhere."""

import platform
import sys
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.audio_io import ANALYSIS_RATE
from podcleaner_editor.config import Settings
from podcleaner_editor.errors import EditorError
from podcleaner_editor.timeline import Interval


class Transcriber(Protocol):
    name: str

    def words(self, audio: np.ndarray, offset: float) -> list[Word]:
        """The words heard in `audio` (mono 16 kHz), times shifted by `offset` seconds."""
        ...


@dataclass(frozen=True)
class TranscriptionInfo:
    backend: str
    speech_s: float
    cached_tracks: int


def _words_from(raw: list[tuple[str, float, float]], offset: float) -> list[Word]:
    words = [
        Word(text.strip(), round(start + offset, 3), round(end + offset, 3))
        for text, start, end in raw
        if text.strip()
    ]
    words.sort(key=lambda w: w.start)
    return words


class _MlxTranscriber:
    def __init__(self, settings: Settings) -> None:
        model = settings.whisper_model
        self.model = model
        self.repo = model if "/" in model else f"mlx-community/whisper-{model}"
        self.name = f"mlx-whisper {model}"
        self._language = settings.transcription_language
        self._prompt = settings.transcription_prompt
        self._loaded = False

    def words(self, audio: np.ndarray, offset: float) -> list[Word]:
        # mlx-whisper loads the model inside transcribe: the first call can fail to load.
        try:
            import mlx_whisper  # imported late: loading it is slow

            result = self._transcribe(mlx_whisper, audio)
        except Exception as exc:
            if self._loaded:
                raise
            raise EditorError(f"Could not load the Whisper model {self.model}: {exc}") from exc
        self._loaded = True
        raw = [
            (w["word"], float(w["start"]), float(w["end"]))
            for segment in result.get("segments", [])
            for w in segment.get("words", [])
        ]
        return _words_from(raw, offset)

    def _transcribe(self, mlx_whisper: Any, audio: np.ndarray) -> Any:
        return mlx_whisper.transcribe(
            audio.astype(np.float32),
            path_or_hf_repo=self.repo,
            language=self._language,
            initial_prompt=self._prompt,
            word_timestamps=True,
            condition_on_previous_text=False,
        )


class _FasterWhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.whisper_model
        self.name = f"faster-whisper {self.model}"
        self._language = settings.transcription_language
        self._prompt = settings.transcription_prompt
        self._model: Any = None

    def words(self, audio: np.ndarray, offset: float) -> list[Word]:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # imported late: loading it is slow

                self._model = WhisperModel(self.model, compute_type="int8")
            except Exception as exc:
                raise EditorError(f"Could not load the Whisper model {self.model}: {exc}") from exc
        segments, _ = self._model.transcribe(
            audio.astype(np.float32),
            language=self._language,
            initial_prompt=self._prompt,
            word_timestamps=True,
            condition_on_previous_text=False,
        )
        raw = [(w.word, float(w.start), float(w.end)) for s in segments for w in (s.words or [])]
        return _words_from(raw, offset)


def make_transcriber(settings: Settings) -> Transcriber:
    """A transcriber for this machine; the model is only loaded on the first call."""
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return _MlxTranscriber(settings)
    return _FasterWhisperTranscriber(settings)


def transcribe_passages(
    samples: np.ndarray, passages: list[Interval], transcriber: Transcriber
) -> list[Word]:
    """The words of every passage, on the time axis of `samples` (mono 16 kHz)."""
    words: list[Word] = []
    for passage in passages:
        chunk = samples[int(passage.start * ANALYSIS_RATE) : int(passage.end * ANALYSIS_RATE)]
        words.extend(transcriber.words(chunk, passage.start))
    words.sort(key=lambda w: w.start)
    return words
