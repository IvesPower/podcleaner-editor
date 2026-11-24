"""Per-person configuration: a TOML file in the user's configuration folder."""

import math
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal, get_args

from platformdirs import user_config_dir

from podcleaner_editor.analysis.words import normalize
from podcleaner_editor.errors import EditorError

APP_NAME = "podcleaner-editor"
CONFIG_ENV_VAR = "PODCLEANER_EDITOR_CONFIG"

Layout = Literal["separate", "mixed"]
LAYOUTS: tuple[str, ...] = get_args(Layout)


@dataclass(frozen=True)
class Settings:
    output_dir: Path | None = None
    layout: Layout = "separate"
    speakers: tuple[str, str] = ("Voice A", "Voice B")
    silence_min_s: float = 1.0
    silence_target_s: float = 0.4
    fade_ms: int = 30
    gate_enabled: bool = True
    gate_threshold_db: float = -30.0
    gate_min_silence_s: float = 0.5
    gate_attack_s: float = 0.010
    gate_release_s: float = 0.1
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 250
    vad_min_silence_ms: int = 100
    level_hop_s: float = 0.01
    bleed_margin_db: float = 10.0
    activity_above_floor_db: float = 12.0
    own_speech_gap_s: float = 0.2
    film_threshold_dbfs: float = -45.0
    film_merge_gap_s: float = 2.0
    film_min_clip_s: float = 3.0
    whisper_model: str = "large-v3-turbo"
    transcription_language: str = "fr"
    # French on purpose: Whisper copies the style of this text, so it writes the hesitations.
    transcription_prompt: str = "Euh, alors, euh… bon, hum, voilà."
    passage_gap_s: float = 1.0
    passage_pad_s: float = 0.2
    filler_words: tuple[str, ...] = ("euh", "heu", "euhm", "hum", "hm")
    filler_pad_s: float = 0.05
    filler_max_s: float = 1.5
    filler_snap_s: float = 0.08
    # Spoken instructions: French on purpose, they are words to recognize.
    marker_trigger: str = "claude"
    marker_cut_words: tuple[str, ...] = (
        "couper",
        "coupe",
        "supprimer",
        "supprime",
        "enlever",
        "enleve",
        "retirer",
        "retire",
    )
    marker_clip_words: tuple[str, ...] = ("ajouter", "ajoute", "extrait", "inserer", "insere")
    marker_min_score: float = 80.0
    marker_pause_s: float = 0.5
    marker_max_s: float = 15.0
    marker_pad_s: float = 0.1
    # Overlap values tuned on the test recording (samples/pedit): the rule flags widely,
    # Claude (M5) is the one that sets backchannels aside.
    overlap_min_s: float = 0.15
    overlap_floor_hold_s: float = 0.5
    overlap_merge_gap_s: float = 0.5
    max_duration_mismatch_s: float = 2.0
    claude_enabled: bool = True
    claude_model: str = "claude-sonnet-5-5"


# (TOML section, TOML key) → (Settings field, comment written above it in the template).
# The order here is the order of the template.
_KEYS: dict[tuple[str, str], tuple[str, str]] = {
    ("paths", "output_dir"): ("output_dir", "Folder where each episode gets its own subfolder."),
    ("recording", "layout"): (
        "layout",
        '"separate": one WAV per voice; "mixed": one stereo WAV with both voices.',
    ),
    ("recording", "speakers"): ("speakers", "First names of the two voices, used as labels."),
    ("silences", "min_s"): ("silence_min_s", "Silences longer than this (seconds) are shortened."),
    ("silences", "target_s"): ("silence_target_s", "Length a long silence is brought down to."),
    ("silences", "fade_ms"): ("fade_ms", "Fade applied on each side of a cut (milliseconds)."),
    ("gate", "enabled"): (
        "gate_enabled",
        "Silence each voice between its sentences, like Logic's Strip Silence.",
    ),
    ("gate", "threshold_db"): ("gate_threshold_db", "A voice is heard above this level (dBFS)."),
    ("gate", "min_silence_s"): (
        "gate_min_silence_s",
        "Shorter quiet moments stay open (seconds).",
    ),
    ("gate", "attack_s"): (
        "gate_attack_s",
        "The gate opens this long before the voice (seconds).",
    ),
    ("gate", "release_s"): (
        "gate_release_s",
        "The gate closes this long after the voice (seconds).",
    ),
    ("vad", "threshold"): ("vad_threshold", "Speech detection threshold (0 to 1)."),
    ("vad", "min_speech_ms"): ("vad_min_speech_ms", "Shortest speech kept (milliseconds)."),
    ("vad", "min_silence_ms"): ("vad_min_silence_ms", "Shortest pause that splits speech."),
    ("levels", "hop_s"): ("level_hop_s", "Length of one level measurement frame (seconds)."),
    ("levels", "bleed_margin_db"): (
        "bleed_margin_db",
        "A voice counts as speaking only above the other voice's level minus this (dB).",
    ),
    ("levels", "above_floor_db"): (
        "activity_above_floor_db",
        "Sound this far above a track's noise floor (dB) is never a silence.",
    ),
    ("levels", "own_speech_gap_s"): (
        "own_speech_gap_s",
        "Dips shorter than this inside one voice's speech are closed (seconds).",
    ),
    ("film", "threshold_dbfs"): ("film_threshold_dbfs", "Film track level that counts as playing."),
    ("film", "merge_gap_s"): ("film_merge_gap_s", "Pauses shorter than this stay in one clip."),
    ("film", "min_clip_s"): ("film_min_clip_s", "Shortest film clip reported (seconds)."),
    ("transcription", "model"): (
        "whisper_model",
        "Whisper model (mlx-community name on Apple silicon).",
    ),
    ("transcription", "language"): ("transcription_language", "Language spoken in the episode."),
    ("transcription", "prompt"): (
        "transcription_prompt",
        "Example text that makes Whisper write the hesitations.",
    ),
    ("transcription", "passage_gap_s"): (
        "passage_gap_s",
        "Speech closer than this is transcribed in one passage (seconds).",
    ),
    ("transcription", "passage_pad_s"): (
        "passage_pad_s",
        "Margin added around each passage (seconds).",
    ),
    ("hesitations", "words"): ("filler_words", "Words counted as hesitations."),
    ("hesitations", "pad_s"): ("filler_pad_s", "Margin cut around a hesitation (seconds)."),
    ("hesitations", "max_s"): (
        "filler_max_s",
        "Longer hesitations are flagged, not cut (seconds).",
    ),
    ("hesitations", "snap_s"): (
        "filler_snap_s",
        "How far a cut edge may move to the quietest point (seconds).",
    ),
    ("markers", "trigger"): (
        "marker_trigger",
        "Word that opens a spoken instruction, at the start of a sentence.",
    ),
    ("markers", "cut_words"): ("marker_cut_words", "Words that make an instruction a cut."),
    ("markers", "clip_words"): (
        "marker_clip_words",
        "Words that make an instruction a clip to add.",
    ),
    ("markers", "min_score"): (
        "marker_min_score",
        "Lowest similarity (0 to 100) for a heard word to count as the trigger.",
    ),
    ("markers", "pause_s"): (
        "marker_pause_s",
        "A pause this long starts or ends an instruction (seconds).",
    ),
    ("markers", "max_s"): ("marker_max_s", "Longest instruction (seconds)."),
    ("markers", "pad_s"): ("marker_pad_s", "Margin cut around an instruction (seconds)."),
    ("overlaps", "min_s"): ("overlap_min_s", "Shortest talk-over flagged (seconds)."),
    ("overlaps", "floor_hold_s"): (
        "overlap_floor_hold_s",
        "How long the first voice must keep talking after it (seconds).",
    ),
    ("overlaps", "merge_gap_s"): (
        "overlap_merge_gap_s",
        "Pauses shorter than this do not end a turn (seconds).",
    ),
    ("episode", "max_duration_mismatch_s"): (
        "max_duration_mismatch_s",
        "Largest duration difference allowed between tracks (seconds).",
    ),
    ("claude", "enabled"): (
        "claude_enabled",
        "Ask Claude (through a logged-in Claude Code) when it is available.",
    ),
    ("claude", "model"): ("claude_model", "Claude model used through Claude Code."),
}
_SECTIONS = {section for section, _ in _KEYS}
_DEFAULTS = Settings()
_FIELD_NAMES = {f.name for f in fields(Settings)}
assert _FIELD_NAMES == {field for field, _ in _KEYS.values()}, "every setting needs a TOML key"


def resolve_config_path(cli_path: Path | None) -> Path:
    """`--config`, else the environment variable, else the user's configuration folder."""
    if cli_path is not None:
        return cli_path
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env)
    return Path(user_config_dir(APP_NAME)) / "config.toml"


def load_settings(path: Path) -> Settings:
    """The settings in `path`; a missing file gives the defaults."""
    if not path.is_file():
        return Settings()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise EditorError(f"{path} is not a valid TOML file: {exc}") from exc
    values: dict[str, Any] = {}
    for section, table in data.items():
        if section not in _SECTIONS or not isinstance(table, dict):
            raise EditorError(f"{path}: unknown section [{section}]")
        for key, raw in table.items():
            if (section, key) not in _KEYS:
                raise EditorError(f"{path}: unknown setting [{section}] {key}")
            name = _KEYS[(section, key)][0]
            label = f"{path}: [{section}] {key}"
            values[name] = _convert(name, raw, label)
            if name in _SINGLE_WORDS:
                _check_single_words(values[name], label)
    return Settings(**values)


# Matched against one transcribed word at a time.
_SINGLE_WORDS = ("marker_trigger", "marker_cut_words", "marker_clip_words")


def _check_single_words(value: str | tuple[str, ...], label: str) -> None:
    words = (value,) if isinstance(value, str) else value
    if any(len(normalize(w).split()) != 1 for w in words):
        many = "single words" if isinstance(value, tuple) else "a single word"
        raise EditorError(f"{label} must be {many}")


def _convert(name: str, raw: Any, label: str) -> Any:
    default = getattr(_DEFAULTS, name)
    if name == "output_dir":
        if not isinstance(raw, str) or not raw.strip():
            raise EditorError(f"{label} must be a folder path")
        return Path(raw).expanduser()
    if name == "layout":
        if raw not in LAYOUTS:
            raise EditorError(f"{label} must be one of: {', '.join(LAYOUTS)}")
        return raw
    if name == "speakers":
        if (
            not isinstance(raw, list)
            or len(raw) != 2
            or not all(isinstance(v, str) and v.strip() for v in raw)
        ):
            raise EditorError(f'{label} must list two names, such as ["Julien", "Marc"]')
        return (raw[0].strip(), raw[1].strip())
    if isinstance(default, tuple):
        if (
            not isinstance(raw, list)
            or not raw
            or not all(isinstance(v, str) and v.strip() for v in raw)
        ):
            raise EditorError(f'{label} must list words, such as ["euh", "heu"]')
        return tuple(v.strip() for v in raw)
    if isinstance(default, bool):
        if not isinstance(raw, bool):
            raise EditorError(f"{label} must be true or false")
        return raw
    if isinstance(default, int):
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise EditorError(f"{label} must be a whole number")
        return raw
    if isinstance(default, float):
        if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
            raise EditorError(f"{label} must be a number")
        return float(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise EditorError(f"{label} must be a text value")
    return raw


def settings_values(s: Settings) -> dict[str, Any]:
    """The settings as a field → value mapping, the input of `render_template`."""
    return {f.name: getattr(s, f.name) for f in fields(Settings)}


def _toml_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, Path):
        return _toml_string(str(value))
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return _toml_string(str(value))


def render_template(values: dict[str, Any]) -> str:
    """The commented configuration file holding `values` (fields missing take the default)."""
    lines = [f"# {APP_NAME} configuration. Every key is optional.", ""]
    current = None
    for (section, key), (name, comment) in _KEYS.items():
        if section != current:
            if current is not None:
                lines.append("")
            lines.append(f"[{section}]")
            current = section
        value = values.get(name, getattr(_DEFAULTS, name))
        lines.append(f"# {comment}")
        if value is None:  # an unset path: shown as an example, commented out
            lines.append(f'# {key} = "/path/to/folder"')
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def write_config(path: Path, text: str) -> None:
    """Writes next to the target first, then renames: an interrupted write leaves no half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f".{path.name}.part")
    try:
        part.write_text(text, encoding="utf-8")
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def write_template(path: Path) -> None:
    """The commented file with the defaults, for someone who prefers to edit it by hand."""
    if path.exists():
        raise EditorError(f"Configuration file already exists: {path}")
    write_config(path, render_template(settings_values(Settings())))


def _shown(value: Any) -> str:
    if value is None:
        return "(not set)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return ", ".join(str(v) for v in value)
    return str(value)


def describe(s: Settings) -> list[tuple[str, str]]:
    """Each setting as (`section.key`, value shown to a person), in the file's order."""
    return [
        (f"{section}.{key}", _shown(getattr(s, name)))
        for (section, key), (name, _) in _KEYS.items()
    ]
