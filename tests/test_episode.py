from dataclasses import replace

import pytest

from podcleaner_editor.config import Settings
from podcleaner_editor.episode import load_episode
from podcleaner_editor.errors import EditorError

NAMED = replace(Settings(), speakers=("Julien", "Marc"))


def test_load_episode_accepts_spaces_accents_float32_and_stereo(make_wav, tmp_path):
    d = tmp_path / "Épisode 12 été"
    a = make_wav(d / "voix julien.wav", seconds=10, subtype="PCM_24")
    b = make_wav(d / "voix marc.wav", seconds=10, channels=2, subtype="FLOAT")
    film = make_wav(d / "film.wav", seconds=10, sr=44100)
    ep = load_episode([a, b], film, "Épisode 12", NAMED)
    assert ep.layout == "separate"
    assert [t.label for t in ep.voices] == ["Julien", "Marc"]
    assert ep.film.label == "Film"
    assert ep.voices[1].info.channels == 2
    assert ep.film.info.sample_rate == 44100
    assert abs(ep.duration - 10) < 0.01


def test_one_voice_file_is_mixed_layout(make_wav, tmp_path):
    voices = make_wav(tmp_path / "voices.wav", seconds=5, channels=2)
    film = make_wav(tmp_path / "film.wav", seconds=5)
    ep = load_episode([voices], film, "ep", NAMED)
    assert ep.layout == "mixed"
    assert len(ep.voices) == 1
    assert ep.voices[0].label == "Julien + Marc"


@pytest.mark.parametrize("count", [0, 3])
def test_zero_or_three_voices_rejected(make_wav, tmp_path, count):
    voices = [make_wav(tmp_path / f"v{i}.wav", seconds=1) for i in range(count)]
    film = make_wav(tmp_path / "film.wav", seconds=1)
    with pytest.raises(EditorError, match="1 or 2 voice files"):
        load_episode(voices, film, "ep", NAMED)


def test_load_episode_rejects_non_wav(make_wav, tmp_path):
    flac = make_wav(tmp_path / "a.flac", seconds=1, subtype="PCM_16")
    film = make_wav(tmp_path / "film.wav", seconds=1)
    with pytest.raises(EditorError, match="WAV only"):
        load_episode([flac], film, "ep", NAMED)


def test_renamed_flac_is_not_a_wav(make_wav, tmp_path):
    fake = make_wav(tmp_path / "fake.wav", seconds=1, subtype="PCM_16", format="FLAC")
    film = make_wav(tmp_path / "film.wav", seconds=1)
    with pytest.raises(EditorError, match="WAV only"):
        load_episode([fake], film, "ep", NAMED)


def test_load_episode_rejects_duration_mismatch(make_wav, tmp_path):
    a = make_wav(tmp_path / "a.wav", seconds=10)
    b = make_wav(tmp_path / "b.wav", seconds=13)
    film = make_wav(tmp_path / "film.wav", seconds=10)
    with pytest.raises(EditorError, match=r"00:00:10\.000.*00:00:13\.000"):
        load_episode([a, b], film, "ep", NAMED)


def test_small_duration_difference_is_accepted(make_wav, tmp_path):
    a = make_wav(tmp_path / "a.wav", seconds=10)
    b = make_wav(tmp_path / "b.wav", seconds=11.5)
    film = make_wav(tmp_path / "film.wav", seconds=10)
    assert abs(load_episode([a, b], film, "ep", NAMED).duration - 10) < 0.01


def test_load_episode_missing_file(make_wav, tmp_path):
    film = make_wav(tmp_path / "film.wav", seconds=1)
    missing = tmp_path / "nope.wav"
    with pytest.raises(EditorError, match="nope.wav"):
        load_episode([missing], film, "ep", NAMED)
