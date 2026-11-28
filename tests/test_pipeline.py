import re
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from conftest import IdentityDenoiser
from typer.testing import CliRunner

from podcleaner_editor import pipeline
from podcleaner_editor.analysis.words import Word
from podcleaner_editor.audio_io import ANALYSIS_RATE, decode_mono_16k
from podcleaner_editor.cli import app
from podcleaner_editor.config import Settings
from podcleaner_editor.cutmap import CutMap
from podcleaner_editor.detect.cuts import OTHER_SPEECH
from podcleaner_editor.episode import load_episode
from podcleaner_editor.errors import EditorError
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.render.markers import Marker, read_wav_markers
from podcleaner_editor.report.markdown import AnalysisResult
from podcleaner_editor.sound.loudness import measure
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
    """Fixed words per voice file; `decode` remembers which file is being transcribed.

    It relies on the pipeline decoding a voice again just before transcribing it.
    """

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
    ("Claude,", 20.0, 20.3),
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
    cutting = replace(SETTINGS, marker_cut_instructions=True)
    result = _analyze(episode, fake, _fake_vad({90: [I(15, 45)], 91: [I(50, 55)]}), cutting)

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


def test_instruction_left_in_the_audio_by_default(quiet_film_files):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    julien = [*_words(("bonjour", 16.0, 16.5)), *MARKER_AT_20, *_words(("alors", 25.0, 25.5))]
    fake = _FakeTranscriber({"julien": julien})
    result = _analyze(episode, fake, _fake_vad({90: [I(15, 45)], 91: [I(50, 55)]}))

    requests = [e for e in result.events if e.type == EventType.CUT_REQUEST]
    assert [(e.start, e.end) for e in requests] == [(20.0, 21.5)]
    assert result.marker_cuts == ()
    assert not any(c.start < 21.5 and c.end > 20.0 for c in result.cuts.cuts)


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


def test_euh_that_swallows_a_gap_is_not_a_silence(quiet_film_files):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    julien = _words(("bonjour", 9.5, 10.0), ("euh", 10.1, 11.3), ("voilà", 11.4, 12.0))
    fake = _FakeTranscriber({"julien": julien})
    vad = _fake_vad({90: [I(5, 10), I(10.1, 11.3), I(11.4, 20)], 91: [I(50, 55)]})
    result = _analyze(episode, fake, vad)
    [filler] = result.fillers
    assert filler.cut is not None
    # Once the "euh" is cut, 10.0-11.4 is a 1.4 s gap: its silence cut lies inside the
    # "euh" cut, so it is counted with the hesitations only.
    assert not [c for c in result.silence_cuts.cuts if c.start < 11.4 and c.end > 10.0]
    assert filler.cut in result.cuts.cuts
    removed = result.silence_cuts.removed() + filler.cut.duration
    assert result.cuts.removed() == pytest.approx(removed)


def test_euh_inside_an_instruction_is_not_counted_twice(quiet_film_files):
    a, b, film = quiet_film_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    julien = _words(
        ("Claude,", 20.0, 20.3),
        ("ici", 20.4, 20.6),
        ("euh", 20.8, 21.0),
        ("on", 21.2, 21.4),
        ("coupe.", 21.5, 21.9),
    )
    fake = _FakeTranscriber({"julien": julien})
    cutting = replace(SETTINGS, marker_cut_instructions=True)
    result = _analyze(episode, fake, _fake_vad({90: [I(19, 23)], 91: [I(50, 55)]}), cutting)
    assert len(result.marker_cuts) == 1
    [filler] = result.fillers
    assert filler.cut is None and filler.reason == "Inside a spoken instruction"


def _mixed_with_words(files, words, speech):
    """Mixed layout, every word transcribed (one passage), the VAD hearing only `speech`."""
    a, _, film = files
    episode = load_episode([a], film, "ep", SETTINGS)
    settings = replace(SETTINGS, passage_gap_s=20.0)
    fake = _FakeTranscriber({"julien": words})
    return _analyze(episode, fake, lambda samples, st: speech, settings)


def test_silence_split_by_a_speech_cut_counts_once(quiet_film_files):
    # Whisper hears an "euh" the VAD left out, in the middle of a long silence.
    words = _words(("bonjour", 19.5, 20.0), ("euh", 25.0, 25.4), ("voilà", 30.0, 30.5))
    result = _mixed_with_words(quiet_film_files, words, [I(15, 20), I(30, 45)])
    [filler] = result.fillers
    assert filler.cut is not None
    inside = [c for c in result.silence_cuts.cuts if 20 < c.start < 30]
    assert len(inside) == 2  # either side of the "euh" cut
    # 0-15 s, 20-30 s, 45-80 s and 85-90 s: four silences, not five.
    assert len(result.silence_cuts.cuts) == 5
    assert result.silences_shortened == 4


def test_silence_sliver_of_one_frame_is_dropped(quiet_film_files):
    # The silence cut starts at 20.2 s; the "euh" cut starts one frame later, at 20.21 s.
    words = _words(("bonjour", 19.5, 20.205), ("euh", 20.25, 20.6), ("voilà", 25.0, 25.5))
    result = _mixed_with_words(quiet_film_files, words, [I(15, 20), I(25, 45)])
    [filler] = result.fillers
    assert filler.cut.start == pytest.approx(20.21)
    assert [c for c in result.silence_cuts.cuts if 20 <= c.start < 25] == [I(filler.cut.end, 24.8)]


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
    download = [s for s in steps if "Whisper model is downloaded" in s]
    assert download == [
        "Transcribing Julien… (the Whisper model is downloaded on first use, about 1.6 GB)"
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
    assert not any("downloaded" in s for s in steps)


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
    path = pipeline.run(
        load_episode([a, b], film, "Episode 7", SETTINGS), SETTINGS, out, dry_run=True
    )[0]
    assert (out / "Episode 7.words.json").is_file()
    assert "### Transcription" in path.read_text(encoding="utf-8")


def test_run_reports_an_unwritable_output_folder(episode_files, tmp_path, monkeypatch):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [I(0, 20)])
    out = tmp_path / "taken"
    out.write_text("a file, not a folder", encoding="utf-8")
    episode = load_episode([a, b], film, "ep", SETTINGS)
    with pytest.raises(EditorError, match=re.escape(f"Could not write to {out}: ")):
        pipeline.run(episode, SETTINGS, out, dry_run=True)


def test_run_reports_an_unwritable_words_cache(episode_files, tmp_path, monkeypatch):
    a, b, film = episode_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda s, st: [I(0, 20)])

    def failing(*args):
        raise PermissionError("read-only")

    monkeypatch.setattr(pipeline, "save_words", failing)
    out = tmp_path / "out"
    episode = load_episode([a, b], film, "ep", SETTINGS)
    with pytest.raises(EditorError, match=re.escape(f"Could not write to {out}: read-only")):
        pipeline.run(episode, SETTINGS, out, dry_run=True)


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


RATE = 8000


def _voice(path: Path, seconds: float, spans=(), amp: float = 0.5, sr: int = RATE) -> Path:
    """A voice track: a 440 Hz tone of amplitude `amp` in each span (all of it if none)."""
    t = np.arange(int(round(seconds * sr))) / sr
    on = np.zeros(len(t), dtype=bool) if spans else np.ones(len(t), dtype=bool)
    for start, end in spans:
        on |= (t >= start) & (t < end)
    sf.write(path, np.where(on, amp * np.sin(2 * np.pi * 440 * t), 0.0), sr, subtype="PCM_16")
    return path


def _capture(monkeypatch) -> list:
    """The results of `analyze` during a run, in order."""
    results = []
    analyze = pipeline.analyze

    def capturing(*args, **kwargs):
        results.append(analyze(*args, **kwargs))
        return results[-1]

    monkeypatch.setattr(pipeline, "analyze", capturing)
    return results


def _midi_markers(path: Path) -> list[tuple[float, str]]:
    """(time in seconds, name) of each marker meta event of a type 0 MIDI file."""
    track = path.read_bytes()[22:]
    pos, tick, found = 7, 0, []  # after the tempo event
    while pos < len(track) - 4:
        delta = 0
        while True:
            byte = track[pos]
            pos += 1
            delta = (delta << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
        tick += delta
        assert track[pos : pos + 2] == b"\xff\x06"
        size = track[pos + 2]  # names are shorter than 128 bytes here
        found.append((tick / 1920, track[pos + 3 : pos + 3 + size].decode("utf-8")))
        pos += 3 + size
    return found


@pytest.fixture
def edit_files(tmp_path):
    """Voices of 30 s and 31 s and a film of 30 s at 8 kHz, each sounding once."""
    a = _voice(tmp_path / "julien.wav", 30, [(2, 8)])
    b = _voice(tmp_path / "franck.wav", 31, [(12, 16)])
    film = _film(tmp_path / "film.wav", 30, (20, 24), sr=RATE)
    return a, b, film


def test_run_writes_every_output(edit_files, tmp_path, monkeypatch):
    a, b, film = edit_files
    monkeypatch.setattr(pipeline, "speech_intervals", _fake_vad({30: [I(2, 8)], 31: [I(12, 16)]}))
    results = _capture(monkeypatch)
    out = tmp_path / "out"
    episode = load_episode([a, b], film, "ep", SETTINGS)
    paths = pipeline.run(episode, SETTINGS, out, dry_run=False)

    names = ["ep.julien.wav", "ep.franck.wav", "ep.film.wav", "ep.mix.wav", "ep.markers.mid"]
    assert paths == [out / "ep.edit.md", *(out / n for n in names)]
    assert all(p.is_file() for p in paths)
    assert not list(out.glob("*.tmp"))
    [result] = results
    cuts = result.cuts
    assert len(cuts.cuts) >= 3
    frames = {sf.info(out / n).frames for n in names[:4]}
    assert len(frames) == 1
    expected = round(cuts.final_duration(episode.duration) * RATE)
    assert abs(frames.pop() - expected) <= len(cuts.cuts)
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert "· mode: edit ·" in text
    assert "### Files\n\n" + "".join(f"- {n}\n" for n in names) in text


def test_markers_match_events_and_flagged_fillers(tmp_path, monkeypatch):
    voices = _voice(tmp_path / "julien.wav", 50)
    film = _film(tmp_path / "film.wav", 50, (0, 0), sr=RATE)
    words = [
        *_words(("bonjour", 16.0, 16.5)),
        *MARKER_AT_20,
        *_words(("alors", 29.0, 29.5), ("euh", 30.0, 30.4), ("oui", 30.2, 30.6)),
        *_words(("bon", 31.0, 31.4)),
    ]
    fake = _FakeTranscriber({"julien": words})
    monkeypatch.setattr(pipeline, "make_transcriber", lambda settings: fake)
    monkeypatch.setattr(pipeline, "decode_mono_16k", fake.decode)
    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, settings: [I(15, 45)])
    settings = replace(SETTINGS, passage_gap_s=20.0, sound_enabled=False)  # markers only
    out = tmp_path / "out"
    pipeline.run(load_episode([voices], film, "ep", settings), settings, out, dry_run=False)

    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    [request] = [r for r in _table_rows(text, "## Timecodes") if r[1] == "Requested cut"]
    [flagged] = _table_rows(text, "### Hesitations")
    expected = [
        (_seconds(request[4]), "Requested cut"),
        (_seconds(flagged[1]), "Hesitation"),
    ]
    midi = _midi_markers(out / "ep.markers.mid")
    wav = [(pos / RATE, name) for pos, name in read_wav_markers(out / "ep.mix.wav")]
    for found in (midi, wav):
        assert [name for _, name in found] == [name for _, name in expected]
        for (time, _), (want, _) in zip(found, expected, strict=True):
            assert time == pytest.approx(want, abs=0.001)


def test_markers_of_never_go_below_zero(edit_files):
    a, b, film = edit_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    late = Event(EventType.OVERLAP, 3.0, 4.0, "Franck", "Reason")
    early = Event(EventType.OVERLAP, -0.01, 1.0, "Franck", "Early")
    result = AnalysisResult(episode, [late, early], CutMap((I(1.0, 2.0),)), True)
    assert pipeline.markers_of(result) == [
        Marker(0.0, "Overlap"),
        Marker(2.0, "Overlap"),
    ]


def test_gate_follows_settings(tmp_path, monkeypatch):
    # A quiet voice, below the gate's -30 dB: the gate shuts it when it is on.
    a = _voice(tmp_path / "julien.wav", 10, amp=0.01)
    b = _voice(tmp_path / "franck.wav", 10, amp=0.01)
    film = _film(tmp_path / "film.wav", 10, (0, 0), sr=RATE)
    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, settings: [I(0, 10)])
    results = _capture(monkeypatch)
    settings = replace(SETTINGS, sound_enabled=False)  # raw levels
    episode = load_episode([a, b], film, "ep", settings)

    pipeline.run(episode, settings, tmp_path / "on", dry_run=False)
    assert results[-1].gates == {"Julien": (), "Franck": ()}
    assert not np.any(sf.read(tmp_path / "on" / "ep.julien.wav")[0])

    off = replace(settings, gate_enabled=False)
    pipeline.run(episode, off, tmp_path / "off", dry_run=False)
    assert results[-1].gates is None
    for name in ("julien", "franck"):
        data, _ = sf.read(tmp_path / "off" / f"ep.{name}.wav")
        assert np.max(np.abs(data)) == pytest.approx(0.01, abs=1e-3)


def test_analyze_gates_use_the_other_voice_when_separate(edit_files):
    a, b, film = edit_files
    episode = load_episode([a, b], film, "ep", SETTINGS)
    result = pipeline.analyze(episode, SETTINGS, vad=lambda s, st: [])
    assert _pairs(result.gates["Julien"]) == [(2, 8)]
    assert _pairs(result.gates["Franck"]) == [(12, 16)]


def test_mixed_layout_outputs(edit_files, tmp_path, monkeypatch):
    a, _, film = edit_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, settings: [I(2, 8)])
    settings = replace(SETTINGS, speakers=("A", "B"))
    out = tmp_path / "out"
    paths = pipeline.run(load_episode([a], film, "ep", settings), settings, out, dry_run=False)
    names = ["ep.edit.md", "ep.a-b.wav", "ep.film.wav", "ep.mix.wav", "ep.markers.mid"]
    assert [p.name for p in paths] == names
    assert sorted(p.name for p in out.iterdir()) == sorted([*names, "ep.words.json"])


def test_dry_run_writes_no_audio(edit_files, tmp_path, monkeypatch):
    a, b, film = edit_files
    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, settings: [I(2, 8)])
    out = tmp_path / "out"
    episode = load_episode([a, b], film, "ep", SETTINGS)
    assert pipeline.run(episode, SETTINGS, out, dry_run=True) == [out / "ep.edit.md"]
    assert sorted(p.name for p in out.iterdir()) == ["ep.edit.md", "ep.words.json"]
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert "· mode: dry run ·" in text
    assert "### Files\n\nNone: dry run, no audio written.\n" in text


def test_run_checks_the_tracks_before_the_analysis(tmp_path, monkeypatch):
    a = _voice(tmp_path / "julien.wav", 10)
    b = _voice(tmp_path / "franck.wav", 10, sr=16000)
    film = _film(tmp_path / "film.wav", 10, (0, 0), sr=RATE)

    def no_analysis(*args, **kwargs):
        raise AssertionError("the tracks should have been checked first")

    monkeypatch.setattr(pipeline, "analyze", no_analysis)
    episode = load_episode([a, b], film, "ep", SETTINGS)
    with pytest.raises(EditorError, match="sample rate"):
        pipeline.run(episode, SETTINGS, tmp_path / "out", dry_run=False)


def test_run_reports_a_track_that_cannot_be_opened(tmp_path):
    a = _voice(tmp_path / "julien.wav", 10)
    b = _voice(tmp_path / "franck.wav", 10)
    film = _film(tmp_path / "film.wav", 10, (0, 0), sr=RATE)
    episode = load_episode([a, b], film, "ep", SETTINGS)
    b.write_bytes(b"not a wav file")
    with pytest.raises(EditorError, match=re.escape("Could not open the tracks: ")):
        pipeline.run(episode, SETTINGS, tmp_path / "out", dry_run=False)


class _RaisingDenoiser:
    name = "raising"
    rate = 8000

    def __call__(self, mono):
        raise AssertionError("no sound should be processed")


def _sound_run(tmp_path, monkeypatch, settings=SETTINGS, voices=None, film_tone=(20, 24), **kwargs):
    """Runs the edit of two 8 kHz voices and a film with sound, returning the output folder."""
    if voices is None:
        voices = (
            _voice(tmp_path / "julien.wav", 30, [(2, 8)], amp=0.05),
            _voice(tmp_path / "franck.wav", 30, [(12, 16)], amp=0.05),
        )
    film = _film(tmp_path / "film.wav", 30, film_tone, sr=RATE)
    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, st: [I(2, 8), I(12, 16)])
    out = tmp_path / "out"
    episode = load_episode(list(voices), film, "ep", settings)
    pipeline.run(episode, settings, out, dry_run=False, **kwargs)
    return out


def _sound_lines(text: str) -> list[str]:
    return text.split("### Sound\n\n", 1)[1].split("\n\n###", 1)[0].splitlines()


def test_run_processes_the_voices_not_the_film(tmp_path, monkeypatch):
    denoised, filtered, written, messages = [], [], [], []
    real_denoise, real_filters = pipeline.denoise_file, pipeline.apply_filters
    real_write = pipeline.write_edit

    def denoise(source, target, denoiser, **kwargs):
        denoised.append(source.name)
        real_denoise(source, target, denoiser, **kwargs)

    def filters(source, target, chain):
        filtered.append(target.name)
        real_filters(source, target, chain)

    def write(tracks, *args, **kwargs):
        written.append((tracks, kwargs["gain_db"]))
        steps.append("write")
        return real_write(tracks, *args, **kwargs)

    steps = []
    real_measure = pipeline.measure

    def measuring(paths):
        steps.append(sorted(p.name for p in paths))
        return real_measure(paths)

    monkeypatch.setattr(pipeline, "measure", measuring)

    made = []

    def make():
        made.append(IdentityDenoiser(RATE))
        return made[-1]

    monkeypatch.setattr(pipeline, "denoise_file", denoise)
    monkeypatch.setattr(pipeline, "apply_filters", filters)
    monkeypatch.setattr(pipeline, "write_edit", write)
    monkeypatch.setattr(pipeline, "make_denoiser", make)
    out = _sound_run(tmp_path, monkeypatch, progress=messages.append)

    assert denoised == ["julien.wav", "franck.wav"]
    assert filtered == [".ep.julien.sound.tmp.wav", ".ep.franck.sound.tmp.wav"]
    assert len(made) == 1 and made[0].calls >= 2  # created once, for the first voice
    [(tracks, gain)] = written
    assert [t.source.name for t in tracks] == [*filtered, "film.wav"]
    assert [t.subtype for t in tracks[:2]] == ["PCM_16", "PCM_16"]
    assert gain != 0.0
    raw = ["film.wav", "franck.wav", "julien.wav"]
    after = [["ep.julien.wav"], ["ep.franck.wav"], ["ep.film.wav"], ["ep.mix.wav"]]
    assert steps == [
        ["julien.wav"],
        ["franck.wav"],
        ["film.wav"],
        raw,  # every raw measure before the write
        [".ep.franck.sound.tmp.wav", ".ep.julien.sound.tmp.wav", "film.wav"],
        "write",
        *after,
    ]
    assert [p.name for p in out.iterdir() if ".tmp" in p.name] == []
    assert [m for m in messages if "sound" in m or "loudness" in m or "Writing" in m] == [
        "Processing the sound of Julien… (the DeepFilterNet model is downloaded on first use)",
        "Processing the sound of Franck…",
        "Measuring the loudness…",
        "Writing the edited tracks…",
        "Measuring the loudness of the written files…",
    ]
    # The film is only scaled by the shared gain.
    film, _ = sf.read(tmp_path / "film.wav", dtype="float32")
    out_film, _ = sf.read(out / "ep.film.wav", dtype="float32")
    assert np.max(np.abs(out_film)) == pytest.approx(
        np.max(np.abs(film)) * 10 ** (gain / 20), abs=1e-4
    )


def test_mix_reaches_the_target_loudness(tmp_path, monkeypatch):
    out = _sound_run(tmp_path, monkeypatch)
    assert measure([out / "ep.mix.wav"]).lufs == pytest.approx(-16.0, abs=0.5)


def test_gain_capped_by_true_peak(tmp_path, monkeypatch):
    # A quiet voice with one loud click: reaching -16 LUFS would push the click past -1 dBTP.
    t = np.arange(30 * RATE) / RATE
    quiet = 0.01 * np.sin(2 * np.pi * 440 * t)
    quiet[5 * RATE] = 0.9
    path = tmp_path / "julien.wav"
    sf.write(path, quiet, RATE, subtype="FLOAT")
    settings = replace(SETTINGS, speakers=("A", "B"), gate_enabled=False, sound_filters="")
    out = _sound_run(tmp_path, monkeypatch, settings, voices=[path], film_tone=(0, 0))
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert "Target not reached: true peak held at -1.0 dBTP." in _sound_lines(text)[0]
    mix = measure([out / "ep.mix.wav"])
    assert mix.true_peak_db <= -0.8
    assert mix.lufs < -17.0


def test_sound_disabled_writes_raw_levels(tmp_path, monkeypatch):
    settings = replace(SETTINGS, sound_enabled=False)
    out = _sound_run(tmp_path, monkeypatch, settings, denoiser=_RaisingDenoiser())
    data, _ = sf.read(out / "ep.julien.wav", dtype="float32")
    assert np.max(np.abs(data)) == pytest.approx(0.05, abs=1e-3)
    assert sf.info(out / "ep.julien.wav").subtype == "PCM_16"
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert _sound_lines(text) == ["Not processed: [sound] enabled = false."]


def test_sound_section_in_edit_file(tmp_path, monkeypatch):
    out = _sound_run(tmp_path, monkeypatch)
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert text.index("### Tracks") < text.index("### Sound") < text.index("### Silences")
    lines = _sound_lines(text)
    assert re.fullmatch(
        r"DeepFilterNet 3 \+ filters · gain [+-]\d+\.\d dB · target -16\.0 LUFS\.", lines[0]
    )
    assert lines[1:3] == ["", "| File | Before | After |"]
    cell = r"-?\d+\.\d LUFS / -?(\d+\.\d|inf) dBTP"
    rows = lines[4:]
    names = ["ep.julien.wav", "ep.franck.wav", "ep.film.wav", "ep.mix.wav"]
    assert [r.split(" | ")[0].lstrip("| ") for r in rows] == names
    for row in rows:
        assert re.fullmatch(rf"\| \S+ \| {cell} \| {cell} \|", row), row
    after_mix = measure([out / "ep.mix.wav"])
    assert rows[3].endswith(f"| {after_mix.lufs:.1f} LUFS / {after_mix.true_peak_db:.1f} dBTP |")


def test_sound_section_names_the_filters_only_chain(tmp_path, monkeypatch):
    plain = replace(SETTINGS, sound_denoise=False)
    out = _sound_run(tmp_path, monkeypatch, plain, denoiser=_RaisingDenoiser())
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert _sound_lines(text)[0].startswith("filters only · gain ")


def test_no_sound_tmp_left_after_an_error(tmp_path, monkeypatch):
    real = pipeline.apply_filters
    calls = []

    def failing(source, target, chain):
        calls.append(target)
        if len(calls) == 2:
            target.write_bytes(b"half written")
            raise EditorError("ffmpeg could not apply the sound filters: boom")
        real(source, target, chain)

    monkeypatch.setattr(pipeline, "apply_filters", failing)
    with pytest.raises(EditorError, match="boom"):
        _sound_run(tmp_path, monkeypatch)
    out = tmp_path / "out"
    assert len(calls) == 2 and calls[0].parent == out
    assert [p.name for p in out.iterdir() if ".tmp" in p.name] == []


def test_dry_run_processes_no_sound(edit_files, tmp_path, monkeypatch):
    a, b, film = edit_files

    def never(*args, **kwargs):
        raise AssertionError("no sound should be processed")

    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, settings: [I(2, 8)])
    monkeypatch.setattr(pipeline, "make_denoiser", never)
    monkeypatch.setattr(pipeline, "apply_filters", never)
    monkeypatch.setattr(pipeline, "measure", never)
    out = tmp_path / "out"
    episode = load_episode([a, b], film, "ep", SETTINGS)
    pipeline.run(episode, SETTINGS, out, dry_run=True, denoiser=_RaisingDenoiser())
    text = (out / "ep.edit.md").read_text(encoding="utf-8")
    assert _sound_lines(text) == ["None: dry run, no audio written."]


def test_pcm24_source_keeps_its_subtype(tmp_path, monkeypatch):
    voices = []
    for name, span in (("julien", (2, 8)), ("franck", (12, 16))):
        path = _voice(tmp_path / f"{name}.wav", 30, [span], amp=0.05)
        data, _ = sf.read(path)
        sf.write(path, data, RATE, subtype="PCM_24")
        voices.append(path)
    out = _sound_run(tmp_path, monkeypatch, voices=voices)
    for name in ("julien", "franck", "film"):
        assert sf.info(out / f"ep.{name}.wav").subtype == "PCM_24"
    assert sf.info(out / "ep.mix.wav").subtype == "FLOAT"


def test_space_check_counts_the_sound_temporaries(tmp_path, monkeypatch):
    seen = []

    def check(sources, n_out, folder, extra_bytes=0):
        seen.append(extra_bytes)
        raise EditorError("Not enough disk space in somewhere")

    monkeypatch.setattr(pipeline, "check_space", check)
    with pytest.raises(EditorError, match="Not enough disk space"):
        _sound_run(tmp_path, monkeypatch)
    # Two mono float voices of 30 s at 8 kHz, and one intermediate file at a time.
    assert seen == [3 * (30 * RATE * 4 + 4096)]
    assert not (tmp_path / "out" / ".ep.julien.sound.tmp.wav").exists()


@pytest.mark.parametrize(
    ("label", "slug"),
    [
        ("Julien + Franck", "julien-franck"),
        ("Élodie", "elodie"),
        ("  --Voice B--  ", "voice-b"),
        ("", "voice"),
        ("!!", "voice"),
    ],
)
def test_file_slug(label, slug):
    assert pipeline.file_slug(label) == slug


def test_voice_slugs_number_duplicates():
    assert pipeline.voice_slugs(["Élodie", "elodie"]) == ["elodie-1", "elodie-2"]
    assert pipeline.voice_slugs(["Julien", "Franck"]) == ["julien", "franck"]


def test_voice_slugs_never_take_the_film_or_mix_names():
    assert pipeline.voice_slugs(["Film", "Mix"]) == ["film-1", "mix-1"]
    assert pipeline.voice_slugs(["film", "Film"]) == ["film-1", "film-2"]
    assert pipeline.voice_slugs(["Julien + Film"]) == ["julien-film"]


JULIEN_WAV = SAMPLES / "pedit-full-piste-1-julien.wav"
FRANCK_WAV = SAMPLES / "pedit-full-piste-2-franck.wav"
FILM_WAV = SAMPLES / "pedit-full-piste-3-film.wav"
# Julien's three spoken instructions and his three "euh"s, checked by ear (22 Nov 2026).
EXPECTED_MARKERS = [("Clip to add", 18.7), ("Requested cut", 27.6), ("Requested cut", 40.3)]
JULIEN_EUH = [13.2, 26.9, 39.7]
FRANCK_EUH = [48.0, 50.9, 51.3]  # over Julien: flagged, not cut


def _seconds(tc: str) -> float:
    hours, minutes, secs = tc.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(secs)


def _table_rows(text: str, section: str) -> list[list[str]]:
    """The data rows (header and rule left out) of the first table under `section`."""
    body = text.split(section, 1)[1].split("\n### ", 1)[0]
    rows = [line for line in body.splitlines() if line.startswith("| ")]
    return [[c.strip() for c in row.strip("|").split(" | ")] for row in rows[2:]]


def _near(found: list[float], expected: list[float]) -> bool:
    return len(found) == len(expected) and all(
        abs(f - e) <= 0.3 for f, e in zip(found, expected, strict=True)
    )


def _run_and_check(tmp_path, voices, name: str) -> str:
    result = _cli(
        *[a for v in voices for a in ("--voice", v)],
        "--film",
        FILM_WAV,
        "--out",
        tmp_path / name,
        "--dry-run",
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / name / f"{name}.edit.md").read_text(encoding="utf-8")
    rows = _table_rows(text, "## Timecodes")
    markers = [(r[1], _seconds(r[3])) for r in rows if r[1] in ("Clip to add", "Requested cut")]
    assert [t for t, _ in markers] == [t for t, _ in EXPECTED_MARKERS]
    assert _near([s for _, s in markers], [s for _, s in EXPECTED_MARKERS])
    assert "3 spoken markers: 2 requested cuts, 1 clip to add; instructions left" in text
    clips = [r for r in rows if r[1] == "Film clip"]
    assert len(clips) == 1 and _near([_seconds(clips[0][3])], [62.27])
    assert _near([_seconds(clips[0][5])], [5.16])
    # The instructions stay in the audio (Julien cuts them himself): the five silences of M1,
    # the one under the "euh" at 13.2 s being left to the "euh".
    assert "5 silences shortened, 00:00:06.7" in text
    assert "mlx-whisper" in text or "faster-whisper" in text

    # The cut "euh"s are not listed in the edit file: read them back from the words cache.
    episode = load_episode(voices, FILM_WAV, name, Settings())
    cache = tmp_path / name / f"{name}.words.json"
    analysed = pipeline.analyze(episode, Settings(), cache_path=cache)
    assert analysed.transcription.backend == "cache"
    cut = [f.word.start for f in analysed.fillers if f.cut is not None]
    assert _near(cut, JULIEN_EUH)
    return text


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_the_test_recording(tmp_path):
    text = _run_and_check(tmp_path, [JULIEN_WAV, FRANCK_WAV], "pedit")
    rows = _table_rows(text, "## Timecodes")
    # The three talk-overs Julien recorded (Franck over Julien), and no other.
    overlaps = [_seconds(r[3]) for r in rows if r[1] == "Overlap"]
    assert _near(overlaps, [47.74, 50.17, 50.8])
    assert all(r[2] == "Voice B" for r in rows if r[1] == "Overlap")
    assert "3 hesitations removed" in text and "3 flagged:" in text
    flagged = _table_rows(text, "### Hesitations")
    assert _near([_seconds(r[0]) for r in flagged], FRANCK_EUH)
    assert all(r[2] == "Voice B" and r[4] == OTHER_SPEECH for r in flagged)


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_the_mixed_test_recording(tmp_path):
    text = _run_and_check(tmp_path, [SAMPLES / "pedit-full.wav"], "mix")
    assert "Not available: both voices are on one track." in text
    # Whisper follows the louder voice: Franck's "euh"s over Julien are not heard.
    assert "3 hesitations removed" in text and "0 flagged." in text


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_dry_run_on_an_amix_of_the_test_recording(tmp_path):
    mixed = tmp_path / "amix.wav"
    inputs = [a for v in (JULIEN_WAV, FRANCK_WAV) for a in ("-i", str(v))]
    command = ["ffmpeg", "-nostdin", "-v", "error", *inputs, "-filter_complex"]
    subprocess.run([*command, "amix=inputs=2:normalize=0", str(mixed)], check=True)
    text = _run_and_check(tmp_path, [mixed], "amix")
    assert "Not available: both voices are on one track." in text
    assert "3 hesitations removed" in text and "0 flagged." in text


@pytest.mark.slow
@pytest.mark.skipif(not SAMPLES.is_dir(), reason="samples/pedit/ is not available")
def test_pedit_edit_outputs(tmp_path):
    name = "pedit"
    result = _cli(
        "--voice",
        JULIEN_WAV,
        "--voice",
        FRANCK_WAV,
        "--film",
        FILM_WAV,
        "--out",
        tmp_path / name,
    )
    assert result.exit_code == 0, result.output
    out = tmp_path / name
    # The default settings name the voices "Voice A" and "Voice B".
    names = ["voice-a", "voice-b", "film", "mix"]
    wavs = [out / f"{name}.{n}.wav" for n in names]
    midi = out / f"{name}.markers.mid"
    for path in [*wavs, midi, out / f"{name}.edit.md", out / f"{name}.words.json"]:
        assert path.is_file(), path

    infos = [sf.info(p) for p in wavs]
    assert len({i.frames for i in infos}) == 1
    assert all(i.samplerate == 44100 and i.subtype == "FLOAT" for i in infos)

    # The written duration is the final duration of the edit file, within 1 ms.
    episode = load_episode([JULIEN_WAV, FRANCK_WAV], FILM_WAV, name, Settings())
    analysed = pipeline.analyze(episode, Settings(), cache_path=out / f"{name}.words.json")
    expected = analysed.cuts.final_duration(episode.duration)
    assert abs(infos[0].frames / 44100 - expected) < 0.001

    # The mix carries as many markers as the MIDI file and the markers of the analysis.
    in_mix = read_wav_markers(wavs[3])
    assert len(in_mix) == len(_midi_markers(midi)) == len(pipeline.markers_of(analysed))

    # The gate is closed between Julien's sentences: at least 0.4 s of exact zeros.
    julien, _ = sf.read(wavs[0], dtype="float32", always_2d=True)
    silent = np.all(julien == 0, axis=1).astype(np.int8)
    edges = np.diff(np.concatenate(([0], silent, [0])))
    runs = np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)
    assert runs.max(initial=0) >= 0.4 * 44100
