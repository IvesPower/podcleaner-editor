from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def write_audio(
    path: Path,
    seconds: float,
    sr: int = 48000,
    channels: int = 1,
    subtype: str = "PCM_24",
    signal: str = "silence",
    format: str | None = None,
) -> Path:
    """Writes a test audio file: silence, or a 440 Hz tone at half scale."""
    n = int(round(seconds * sr))
    if signal == "tone":
        mono = 0.5 * np.sin(2 * np.pi * 440 * np.arange(n) / sr)
    elif signal == "silence":
        mono = np.zeros(n)
    else:
        raise ValueError(f"unknown signal {signal!r}")
    data = np.repeat(mono[:, None], channels, axis=1) if channels > 1 else mono
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sr, subtype=subtype, format=format)
    return path


@pytest.fixture
def make_wav() -> Callable[..., Path]:
    return write_audio


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path_factory, monkeypatch):
    """Tests never read the configuration file of the person running them."""
    path = tmp_path_factory.mktemp("config") / "config.toml"
    monkeypatch.setenv("PODCLEANER_EDITOR_CONFIG", str(path))
    return path
