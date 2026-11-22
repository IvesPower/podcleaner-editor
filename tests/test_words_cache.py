import json
import os
from dataclasses import replace
from pathlib import Path

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.analysis.words_cache import cache_key, load_words, save_words
from podcleaner_editor.config import Settings
from podcleaner_editor.timeline import Interval

PASSAGES = [Interval(1.0, 2.5), Interval(10.0004, 12.0)]
WORDS = [Word("bonjour", 1.1, 1.5), Word("é", 2.0, 2.25)]


def _setup(tmp_path: Path, make_wav, name: str = "voice.wav", seconds: float = 0.5):
    wav = make_wav(tmp_path / name, seconds)
    return wav, tmp_path / "words.json"


def test_round_trip(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    key = cache_key(wav, PASSAGES, Settings())
    save_words(cache, "julien", key, WORDS)
    assert load_words(cache, "julien", cache_key(wav, PASSAGES, Settings())) == WORDS


def test_key_survives_json(tmp_path, make_wav):
    wav, _ = _setup(tmp_path, make_wav)
    key = cache_key(wav, PASSAGES, Settings())
    assert json.loads(json.dumps(key)) == key


def test_two_tracks_in_one_file(tmp_path, make_wav):
    wav_a, cache = _setup(tmp_path, make_wav, "a.wav")
    wav_b, _ = _setup(tmp_path, make_wav, "b.wav", 0.7)
    key_a = cache_key(wav_a, PASSAGES, Settings())
    key_b = cache_key(wav_b, PASSAGES, Settings())
    other = [Word("salut", 3.0, 3.4)]
    save_words(cache, "a", key_a, WORDS)
    save_words(cache, "b", key_b, other)
    assert load_words(cache, "a", key_a) == WORDS
    assert load_words(cache, "b", key_b) == other
    assert load_words(cache, "c", key_a) is None


def test_missing_file_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    assert load_words(cache, "a", cache_key(wav, PASSAGES, Settings())) is None


def test_changed_file_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    save_words(cache, "a", cache_key(wav, PASSAGES, Settings()), WORDS)
    make_wav(wav, 0.9)  # a different length, so a different size
    assert load_words(cache, "a", cache_key(wav, PASSAGES, Settings())) is None


def test_touched_file_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    save_words(cache, "a", cache_key(wav, PASSAGES, Settings()), WORDS)
    stat = wav.stat()
    os.utime(wav, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert load_words(cache, "a", cache_key(wav, PASSAGES, Settings())) is None


def test_changed_prompt_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    save_words(cache, "a", cache_key(wav, PASSAGES, Settings()), WORDS)
    other = replace(Settings(), transcription_prompt="another prompt")
    assert load_words(cache, "a", cache_key(wav, PASSAGES, other)) is None


def test_changed_passages_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    save_words(cache, "a", cache_key(wav, PASSAGES, Settings()), WORDS)
    assert load_words(cache, "a", cache_key(wav, PASSAGES[:1], Settings())) is None


def test_truncated_json_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    cache.write_text('{"version": 1, "tra', encoding="utf-8")
    key = cache_key(wav, PASSAGES, Settings())
    assert load_words(cache, "a", key) is None
    save_words(cache, "a", key, WORDS)  # starts a fresh file over the broken one
    assert load_words(cache, "a", key) == WORDS


def test_wrong_shape_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    key = cache_key(wav, PASSAGES, Settings())
    cache.write_text('{"version": 1, "tracks": []}', encoding="utf-8")
    assert load_words(cache, "a", key) is None


def test_bad_word_entries_miss(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    key = cache_key(wav, PASSAGES, Settings())
    for words in ([["a", 1.0]], [[1, 1.0, 2.0]], ["abc"], [["a", "x", 2.0]], "oops"):
        entry = {"version": 1, "tracks": {"a": {"key": key, "words": words}}}
        cache.write_text(json.dumps(entry), encoding="utf-8")
        assert load_words(cache, "a", key) is None


def test_not_utf8_misses(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    cache.write_bytes(b"\xff\xfe\x00bad")
    assert load_words(cache, "a", cache_key(wav, PASSAGES, Settings())) is None


def test_no_temporary_file_left(tmp_path, make_wav):
    wav, cache = _setup(tmp_path, make_wav)
    save_words(cache, "a", cache_key(wav, PASSAGES, Settings()), WORDS)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["voice.wav", "words.json"]
