"""Words of each voice track kept in a JSON file, so a second run does not transcribe again."""

import json
import os
from numbers import Real
from pathlib import Path
from typing import Any

from podcleaner_editor.analysis.words import Word
from podcleaner_editor.config import Settings
from podcleaner_editor.timeline import Interval

_VERSION = 1


def cache_key(path: Path, passages: list[Interval], settings: Settings) -> dict[str, Any]:
    """What the words depend on, in a form that compares equal after a JSON round trip."""
    stat = path.stat()
    return {
        "file": path.name,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "whisper_model": settings.whisper_model,
        "language": settings.transcription_language,
        "prompt": settings.transcription_prompt,
        "passages": [[round(p.start, 3), round(p.end, 3)] for p in passages],
    }


def _read(cache_path: Path) -> dict[str, Any] | None:
    """The cache content, or None when it is missing, unreadable or not the expected shape."""
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        return None
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        return None
    if not isinstance(data.get("tracks"), dict):
        return None
    return data


def _is_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _parse_words(raw: object) -> list[Word] | None:
    if not isinstance(raw, list):
        return None
    words = []
    for entry in raw:
        if not (isinstance(entry, list) and len(entry) == 3):
            return None
        text, start, end = entry
        if not (isinstance(text, str) and _is_number(start) and _is_number(end)):
            return None
        words.append(Word(text, float(start), float(end)))
    return words


def load_words(cache_path: Path, label: str, key: dict[str, Any]) -> list[Word] | None:
    """The cached words of track `label`, or None when absent or made with another key."""
    data = _read(cache_path)
    if data is None:
        return None
    entry = data["tracks"].get(label)
    if not isinstance(entry, dict) or entry.get("key") != key:
        return None
    return _parse_words(entry.get("words"))


def save_words(cache_path: Path, label: str, key: dict[str, Any], words: list[Word]) -> None:
    """Stores the words of `label`, keeping the other tracks; a broken file starts afresh."""
    data = _read(cache_path) or {"version": _VERSION, "tracks": {}}
    data["tracks"][label] = {"key": key, "words": [[w.text, w.start, w.end] for w in words]}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    part = cache_path.with_name(f".{cache_path.name}.part")
    try:
        part.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(part, cache_path)
    finally:
        part.unlink(missing_ok=True)
