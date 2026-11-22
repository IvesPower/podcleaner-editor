import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from podcleaner_editor import pipeline
from podcleaner_editor.analysis.words import Word
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k
from podcleaner_editor.cli import app
from podcleaner_editor.config import Settings
from podcleaner_editor.detect.cuts import OTHER_SPEECH
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


class _NoWords:
    name = "no words"

    def words(self, audio, offset):
        return []


@pytest.fixture(autouse=True)
def _no_whisper(request, monkeypatch):
    """Fast tests never load Whisper: the default transcriber hears no words."""
    if request.node.get_closest_marker("slow") is None:
        monkeypatch.setattr(pipeline, "make_transcriber", lambda settings: _NoWords())


class _FakeTranscriber:
    """Fixed words per voice file; `decode` remembers which file is being transcribed."""

    name = "fake whisper"

    def __init__(self, words_by_stem: dict[str, list[Word]]):
        self.words_by_stem = words_by_stem
        self.track = ""

    def decode(self, path):
        self.track = path.stem
        return decode_mono_16k(path)

    def words(self, audio, offset):
        end = offset + len(audio) / ANALYSIS_RATE
        found = self.words_by_stem.get(self.track, [])
        return [w for w in found if offset <= (w.start + w.end) / 2 <= end]


class _Raising:
    name = "raising"

    def words(self, audio, offset):
        raise AssertionError("the cache should have been read")


def _words(*items: tuple[str, float, float]) -> list[Word]:
    return [Word(text, start, end) for text, start, end in items]


MARKER_AT_20 = _words(
    ("Claude", 20.0, 20.3),
    ("ici", 20.3, 20.5),
    ("on", 20.5, 20.7),
    ("veut", 20.7, 21.0),
    ("couper", 21.0, 21.5),
)


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


@pytest.fixture
def quiet_film_files(make_wav, tmp_path):
    """Voices of 90 s and 91 s, the film playing only from 80 s to 85 s."""
    a = make_wav(tmp_path / "julien.wav", seconds=90)
    b = make_wav(tmp_path / "franck.wav", seconds=91)
    film = _film(tmp_path / "film.wav", 90, (80, 85))
    return a, b, film


def _analyze(episode, transcriber, vad, settings=SETTINGS, **kwargs):
    return pipeline.analyze(
        episode, settings, decode=transcriber.decode, vad=vad, transcriber=transcriber, **kwargs
    )


def test_marker_and_filler_in_result(quiet_film_files):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    julien = [*_words(("bonjour", 16.0, 16.5)), *MARKER_AT_20, *_words(("alors", 25.0, 25.5))]
    julien += _words(("euh", 40.0, 40.4), ("voilà", 41.0, 41.5))
    fake = _FakeTranscriber({"julien": julien})
    result = _analyze(episode, fake, _fake_vad({90: [I(15, 45)], 91: [I(50, 55)]}))

    requests = [e for e in result.events if e.type == EventType.CUT_REQUEST]
    assert [(e.track, e.start, e.end) for e in requests] == [("Julien", 20.0, 21.5)]
    assert len(result.marker_cuts) == 1
    [filler] = result.fillers
    assert filler.cut is not None and filler.word.text == "euh"
    marker_cut, filler_cut = result.marker_cuts[0], filler.cut
    assert marker_cut.start <= 20.0 and marker_cut.end >= 21.5
    assert filler_cut.start <= 40.0 and filler_cut.end >= 40.4

    # The film clip at 80 s moves back by the silences around the speech (0-15 s, 45-50 s,
    # 55-80 s, each keeping 0.4 s: 43.8 s) and by both speech cuts.
    expected = 80 - 43.8 - marker_cut.duration - filler_cut.duration
    assert result.cuts.to_final(80) == pytest.approx(expected)
    assert result.transcription.backend == "fake whisper"


def test_bleed_word_counted_once(quiet_film_files):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    settings = replace(SETTINGS, passage_gap_s=3.0)  # Franck's passage spans Julien's phrase
    franck = [*_words(("oui", 18.5, 19.0)), *MARKER_AT_20, *_words(("non", 22.2, 22.6))]
    fake = _FakeTranscriber({"julien": MARKER_AT_20, "franck": franck})
    vad = _fake_vad({90: [I(19.8, 21.6)], 91: [I(18.0, 19.5), I(22.0, 23.0)]})
    result = _analyze(episode, fake, vad, settings)
    markers = [e for e in result.events if e.type == EventType.CUT_REQUEST]
    assert [e.track for e in markers] == ["Julien"]


def test_euh_between_pauses_leaves_one_short_pause(quiet_film_files):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    julien = _words(("bonjour", 19.5, 20.0), ("euh", 20.7, 21.1), ("voilà", 21.8, 22.3))
    fake = _FakeTranscriber({"julien": julien})
    vad = _fake_vad({90: [I(10, 20), I(20.7, 21.1), I(21.8, 30)], 91: [I(50, 55)]})
    result = _analyze(episode, fake, vad)
    assert [f.cut is not None for f in result.fillers] == [True]
    kept = result.cuts.to_final(21.8) - result.cuts.to_final(20.0)
    assert kept == pytest.approx(SETTINGS.silence_target_s)


def test_second_run_reads_the_cache(quiet_film_files, tmp_path):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    julien = [*_words(("bonjour", 16.0, 16.5)), *MARKER_AT_20, *_words(("euh", 40.0, 40.4))]
    fake = _FakeTranscriber({"julien": julien, "franck": _words(("oui", 51.0, 51.5))})
    vad = _fake_vad({90: [I(15, 45)], 91: [I(50, 55)]})
    cache = tmp_path / "out" / "ep.words.json"
    steps: list[str] = []
    first = _analyze(episode, fake, vad, cache_path=cache, progress=steps.append)
    assert cache.is_file()
    download = [s for s in steps if "downloads the Whisper model" in s]
    assert download == [
        "Transcribing Julien… (the first run downloads the Whisper model, about 1.6 GB)"
    ]
    assert "Transcribing Franck…" in steps
    assert first.transcription.cached_tracks == 0

    raising = _Raising()
    raising.decode = fake.decode
    steps.clear()
    second = _analyze(episode, raising, vad, cache_path=cache, progress=steps.append)
    assert second.events == first.events
    assert second.fillers == first.fillers
    assert second.cuts == first.cuts
    assert second.transcription.cached_tracks == 2
    assert second.transcription.backend == "cache"
    assert second.transcription.speech_s == first.transcription.speech_s
    assert not any("downloads" in s for s in steps)


def test_transcriber_created_only_on_a_cache_miss(quiet_film_files, tmp_path, monkeypatch):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    vad = _fake_vad({90: [I(15, 45)], 91: [I(50, 55)]})
    cache = tmp_path / "ep.words.json"
    pipeline.analyze(episode, SETTINGS, vad=vad, cache_path=cache)

    def no_transcriber(settings):
        raise AssertionError("everything is in the cache")

    monkeypatch.setattr(pipeline, "make_transcriber", no_transcriber)
    result = pipeline.analyze(episode, SETTINGS, vad=vad, cache_path=cache)
    assert result.transcription.cached_tracks == 2


def test_mixed_layout_fillers(quiet_film_files):
    a, _, film = quiet_film_files
    episode = load_episode([a], film, "ep", SETTINGS)
    words = _words(
        ("alors", 19.0, 19.5),
        ("euh", 20.0, 20.4),
        ("oui", 20.2, 20.6),  # the other voice, on the same track
        ("bon", 21.0, 21.4),
        ("euh", 40.0, 40.4),
        ("voilà", 41.0, 41.5),
    )
    fake = _FakeTranscriber({"julien": words})
    result = _analyze(episode, fake, lambda samples, settings: [I(18, 45)])
    assert [(f.word.start, f.cut is not None, f.reason) for f in result.fillers] == [
        (20.0, False, OTHER_SPEECH),
        (40.0, True, "Isolated hesitation"),
    ]
    assert result.fillers[0].track == "Julien + Franck"


def test_run_writes_the_words_cache(episode_files, tmp_path, monkeypatch):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [I(0, 20)])
    out = tmp_path / "Episode 7"
    path = pipeline.run(load_episode([a, b], film, "Episode 7", SETTINGS), SETTINGS, out)
    assert (out / "Episode 7.words.json").is_file()
    assert "### Transcription" in path.read_text(encoding="utf-8")


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
    _check_common(text)


def _check_common(text: str) -> None:
    """What both layouts find on the test recording."""
    assert text.count("| Film clip |") == 1
    assert "| Film clip | Film | 00:01:02.2" in text and "| 00:00:05.1" in text
    # M1's five silences (6.8 s), plus the gap the long "euh" at 13.2 s leaves once cut;
    # the "euh" at 26.9 s also lengthens the silence before it.
    assert "6 silences shortened, 00:00:07.8" in text
    assert "hesitations removed" in text
    assert "mlx-whisper" in text or "faster-whisper" in text


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_the_mixed_test_recording(tmp_path):
    film = SAMPLES / "pedit-full-piste-3-film.wav"
    voices = SAMPLES / "pedit-full.wav"
    result = _cli("--voice", voices, "--film", film, "--out", tmp_path / "mix", "--dry-run")
    assert result.exit_code == 0, result.output
    text = (tmp_path / "mix" / "mix.edit.md").read_text(encoding="utf-8")
    assert "Not available: both voices are on one track." in text
    _check_common(text)


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_an_amix_of_the_test_recording(tmp_path):
    voices = [SAMPLES / "pedit-full-piste-1-julien.wav", SAMPLES / "pedit-full-piste-2-franck.wav"]
    mixed = tmp_path / "amix.wav"
    inputs = [a for v in voices for a in ("-i", str(v))]
    command = ["ffmpeg", "-nostdin", "-v", "error", *inputs, "-filter_complex"]
    subprocess.run([*command, "amix=inputs=2:normalize=0", str(mixed)], check=True)
    film = SAMPLES / "pedit-full-piste-3-film.wav"
    result = _cli("--voice", mixed, "--film", film, "--out", tmp_path / "amix", "--dry-run")
    assert result.exit_code == 0, result.output
    text = (tmp_path / "amix" / "amix.edit.md").read_text(encoding="utf-8")
    assert "Not available: both voices are on one track." in text
    _check_common(text)
