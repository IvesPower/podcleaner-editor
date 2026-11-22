from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from podcleaner_editor import pipeline
from podcleaner_editor.cli import app
from podcleaner_editor.config import Settings
from podcleaner_editor.episode import load_episode
from podcleaner_editor.errors import EditorError
from podcleaner_editor.events import EventType
from podcleaner_editor.timeline import Interval as I

SETTINGS = replace(Settings(), speakers=("Julien", "Franck"))
SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "pedit"


def _film(path: Path, seconds: float, tone: tuple[float, float], sr: int = 48000) -> Path:
    """A film track silent except for a tone between `tone` start and end (seconds)."""
    t = np.arange(int(seconds * sr)) / sr
    data = np.where((t >= tone[0]) & (t < tone[1]), 0.5 * np.sin(2 * np.pi * 440 * t), 0.0)
    sf.write(path, data, sr, subtype="PCM_24")
    return path


def _fake_vad(by_length: dict[int, list[I]]):
    """A VAD that answers by the number of samples (each fake voice track has its own length)."""

    def vad(samples, settings):
        return by_length[len(samples) // 16000]

    return vad


@pytest.fixture
def episode_files(make_wav, tmp_path):
    a = make_wav(tmp_path / "julien.wav", seconds=90)
    b = make_wav(tmp_path / "franck.wav", seconds=91)
    film = _film(tmp_path / "film.wav", 90, (30, 60))
    return a, b, film


def _pairs(intervals):
    return [(round(i.start, 2), round(i.end, 2)) for i in intervals]


def test_analyze_with_fake_vad(episode_files):
    a, b, film = episode_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    vad = _fake_vad({90: [I(0, 20)], 91: [I(25, 28)]})
    result = pipeline.analyze(episode, SETTINGS, vad=vad)
    clips = [e for e in result.events if e.type == EventType.FILM_CLIP]
    assert _pairs(clips) == [(30, 60)]
    assert clips[0].track == "Film" and clips[0].reason == "Activity on the film track"
    assert _pairs(result.silence_cuts.cuts) == [(20.2, 24.8), (28.2, 29.8), (60.2, 89.8)]
    assert result.dry_run


def test_analyze_flags_overlaps(episode_files):
    a, b, film = episode_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    result = pipeline.analyze(episode, SETTINGS, vad=_fake_vad({90: [I(0, 20)], 91: [I(5, 6)]}))
    overlaps = [e for e in result.events if e.type == EventType.OVERLAP]
    assert [(e.track, e.start, e.end) for e in overlaps] == [("Franck", 5, 6)]


def test_analyze_mixed_layout(episode_files):
    a, _, film = episode_files
    episode = load_episode([a], film, "ep", SETTINGS)
    seen = []

    def vad(samples, settings):
        seen.append(len(samples))
        return [I(0, 20), I(5, 6), I(25, 28)]

    result = pipeline.analyze(episode, SETTINGS, vad=vad)
    assert len(seen) == 1  # only the voices track goes through the VAD
    assert not any(e.type == EventType.OVERLAP for e in result.events)
    assert _pairs(result.silence_cuts.cuts) == [(20.2, 24.8), (28.2, 29.8), (60.2, 89.8)]


def test_analyze_reports_progress(episode_files):
    a, b, film = episode_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    steps = []
    pipeline.analyze(episode, SETTINGS, vad=lambda s, st: [], progress=steps.append)
    assert steps[0].startswith("Decoding") and len(steps) >= 3


def _cli(*args):
    return CliRunner().invoke(app, ["run", *map(str, args)])


def test_cli_dry_run_writes_md(episode_files, tmp_path, monkeypatch):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [I(0, 20)])
    out = tmp_path / "Episode 42"
    result = _cli("--voice", a, "--voice", b, "--film", film, "--out", out, "--dry-run")
    assert result.exit_code == 0, result.output
    md = out / "Episode 42.edit.md"
    assert md.is_file()
    assert str(md) in result.output
    assert md.read_text(encoding="utf-8").startswith("# Episode 42: edit file")
    assert not list(out.glob("*.wav"))


def test_cli_name_option(episode_files, tmp_path, monkeypatch):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [])
    out = tmp_path / "out"
    args = ["--voice", a, "--voice", b, "--film", film, "--out", out, "--name", "Ep 1"]
    result = _cli(*args, "--dry-run")
    assert result.exit_code == 0, result.output
    assert (out / "Ep 1.edit.md").is_file()


def test_cli_uses_output_dir_from_config(episode_files, tmp_path, monkeypatch, _isolated_config):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [])
    root = tmp_path / "Episodes"
    _isolated_config.write_text(f'[paths]\noutput_dir = "{root.as_posix()}"\n', encoding="utf-8")
    args = ["--voice", a, "--voice", b, "--film", film, "--name", "Ep 2", "--dry-run"]
    result = _cli(*args)
    assert result.exit_code == 0, result.output
    assert (root / "Ep 2" / "Ep 2.edit.md").is_file()


def test_cli_warns_when_files_disagree_with_layout(episode_files, tmp_path, monkeypatch):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [])
    result = _cli("--voice", a, "--film", film, "--out", tmp_path / "ep", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "⚠" in result.output and "mixed" in result.output


def test_cli_without_dry_run_exits_2(episode_files, tmp_path):
    a, b, film = episode_files
    result = _cli("--voice", a, "--voice", b, "--film", film, "--out", tmp_path / "ep")
    assert isinstance(result.exception, EditorError)  # main() turns it into exit code 2
    assert "--dry-run" in str(result.exception)


def test_cli_needs_out_or_output_dir(episode_files):
    a, b, film = episode_files
    result = _cli("--voice", a, "--voice", b, "--film", film, "--name", "ep", "--dry-run")
    assert isinstance(result.exception, EditorError)  # main() turns it into exit code 2
    message = str(result.exception)
    assert "--out" in message and "init`" in message  # the command name is the one typed


def test_cli_needs_a_name_without_out(episode_files):
    a, b, film = episode_files
    result = _cli("--voice", a, "--voice", b, "--film", film, "--dry-run")
    assert isinstance(result.exception, EditorError)  # main() turns it into exit code 2
    assert "--name" in str(result.exception)


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_the_test_recording(tmp_path):
    voices = ["pedit-full-piste-1-julien.wav", "pedit-full-piste-2-franck.wav"]
    args = [a for v in voices for a in ("--voice", SAMPLES / v)]
    film = SAMPLES / "pedit-full-piste-3-film.wav"
    result = _cli(*args, "--film", film, "--out", tmp_path / "pedit", "--dry-run")
    assert result.exit_code == 0, result.output
    text = (tmp_path / "pedit" / "pedit.edit.md").read_text(encoding="utf-8")
    assert "| Film clip |" in text
    # The three talk-overs Julien recorded (Franck over Julien), and no other.
    assert text.count("| Overlap |") == 3
    for start in ("00:00:47.", "00:00:50.1", "00:00:50.8"):
        assert f"| Overlap | Voice B | {start}" in text


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_the_mixed_test_recording(tmp_path):
    film = SAMPLES / "pedit-full-piste-3-film.wav"
    voices = SAMPLES / "pedit-full.wav"
    result = _cli("--voice", voices, "--film", film, "--out", tmp_path / "mix", "--dry-run")
    assert result.exit_code == 0, result.output
    text = (tmp_path / "mix" / "mix.edit.md").read_text(encoding="utf-8")
    assert "| Film clip |" in text
    assert "Not available: both voices are on one track." in text
