"""Per-person configuration: a TOML file in the user's configuration folder."""

import math
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal, get_args

from platformdirs import user_config_dir

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
            values[name] = _convert(name, raw, f"{path}: [{section}] {key}")
    return Settings(**values)


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
