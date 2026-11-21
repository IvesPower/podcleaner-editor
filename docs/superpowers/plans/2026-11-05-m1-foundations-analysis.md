# M1: foundations and analysis, implementation plan

[Français](2026-11-05-m1-foundations-analysis.fr.md) · **English**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a `pedit run … --dry-run` CLI that reads an episode (two voice tracks, or one stereo track holding both voices, plus the film track), detects silences, overlaps and film clips, and writes the `.md` edit file with timecodes on the original audio and on the expected final audio; plus the `pedit init` wizard and the pixel-art banner.

**Architecture:** Python package `src/podcleaner_editor/`. Input/output (ffmpeg, Silero VAD, files, console) stays at the edges; all detection is pure functions over lists of `Interval`, testable without audio. Analysis runs on a 16 kHz mono float32 copy of each track, decoded by ffmpeg, never on the full-resolution audio. The CLI look (banner, wizard, config file) follows podcleaner-clips (`~/dev/podcleaner-clips`, modules `banner.py`, `wizard.py`, `config.py`, `claude.py`), adapted rather than imported.

**Tech Stack:** Python 3.11–3.12, uv, Typer, Rich, platformdirs, numpy, soundfile, silero-vad (ONNX), ffmpeg/ffprobe (on PATH), pytest, Ruff.

**Spec:** [`docs/spec.md`](../../spec.md) (translation of [`docs/spec.fr.md`](../../spec.fr.md), the reference) · roadmap: [`2026-11-05-roadmap.md`](2026-11-05-roadmap.md)

## Global Constraints

- Runs on macOS and Windows; paths via `pathlib`, never hard-coded; text files written with `encoding="utf-8"`.
- No Claude needed; M1 calls no network service at runtime. Claude is only ever reached through the logged-in Claude Code CLI, never an API key or the `anthropic` SDK.
- Input: WAV only. Layout `separate` = 2 voice WAVs + 1 film WAV; layout `mixed` = 1 WAV holding both voices + 1 film WAV.
- Mixed layout: no overlap detection; everything else runs.
- All analysis runs on the original audio; the cut map maps every timecode onto the final audio.
- Silences: every silence > 1 s where all tracks are quiet is brought down to about 0.4 s.
- Overlaps: timecode only, no volume change.
- One `.md` file per episode: Timecodes part, then Report part.
- `--dry-run` writes the report and timecodes without writing audio.
- Everything in English: identifiers, comments, docstrings, messages, errors, CLI help, the edit file, configuration keys.
- Timecodes formatted `HH:MM:SS.mmm`.
- Fast tests (`pytest -m "not slow"`) use no model and no network; tests that load Silero are marked `slow`.
- Each task is done on its own branch and lands in `main` through a pull request; commit and PR titles `type(scope): English / français`, PR description English then French with a `## TL;DR` each (`.github/pull_request_template.md`).
- Documentation in English (`name.md`) and French (`name.fr.md`): any doc that changes changes in both languages.

## Review Focus

1. **Mic bleed**: each mic picks up the other voice; without a filter, all speech becomes an overlap. A track only counts as active when its level is above the other voice's level minus `bleed_margin_db` (10 dB). Test in task 5.
2. **Laughs, breaths, "mmh"**: Silero does not always classify them as speech; they must not be shortened as silences. A silence also requires that no track is above its noise floor + 12 dB. Test in task 7.
3. **Mixed layout**: one voice file must run the whole analysis without overlaps and say so in the report, never compare the track with itself. Tests in tasks 4, 9 and 10.
4. **Tracks with different durations or sample rates** (recording started at different times): duration gap > 2 s → clear error; different sample rates are accepted. Test in task 4.
5. **Paths with spaces and accents, stereo / 24-bit / float 32 WAV, ffmpeg missing**: read without error; a missing ffmpeg gives a message saying what to install, exit code 2, no traceback. Test in task 4.

---

## Files

```
pyproject.toml, uv.lock, .python-version
.github/workflows/ci.yml               (copied from podcleaner-clips)
.claude/settings.json, .claude/skills/graphify/, .gitignore   (graphify setup from podcleaner-clips)
src/podcleaner_editor/__init__.py      __version__, prog_name
src/podcleaner_editor/cli.py           Typer app: init, run, config, version; main()
src/podcleaner_editor/errors.py        EditorError (user message, exit code 2)
src/podcleaner_editor/banner.py        pixel-art title
src/podcleaner_editor/wizard.py        init questions
src/podcleaner_editor/claude_cli.py    find_cli, cli_logged_in (completed in M5)
src/podcleaner_editor/timeline.py      Interval and operations, format_tc
src/podcleaner_editor/config.py        Settings, TOML loading, config path, commented template
src/podcleaner_editor/audio_io.py      probe, decode_mono_16k, frame_levels
src/podcleaner_editor/episode.py       Track, Episode, load_episode
src/podcleaner_editor/analysis/vad.py       speech_intervals (Silero)
src/podcleaner_editor/analysis/activity.py  own_speech, loud_intervals, noise_floor_db
src/podcleaner_editor/analysis/film.py      film_activity, film_clips
src/podcleaner_editor/detect/silences.py    find_silence_cuts
src/podcleaner_editor/detect/overlaps.py    find_overlap_attempts
src/podcleaner_editor/events.py        EventType, Event
src/podcleaner_editor/cutmap.py        CutMap
src/podcleaner_editor/report/markdown.py    AnalysisResult, render_edit_file
src/podcleaner_editor/pipeline.py      analyze, run
tests/…                                one test file per module, tests/data/ for speech
```

---

### Task 1: repository scaffold and minimal CLI

**Files:**
- Create: `pyproject.toml`, `.python-version` (`3.12`), `.github/workflows/ci.yml`, `src/podcleaner_editor/__init__.py`, `src/podcleaner_editor/cli.py`, `src/podcleaner_editor/errors.py`, `tests/test_cli.py`
- Modify: `.claude/settings.json`, `.gitignore`, `CONTRIBUTING.md` / `CONTRIBUTING.fr.md` (graphify)

**Interfaces:**
- Produces: `podcleaner_editor.__version__: str = "0.1.0"`; `podcleaner_editor.cli.app: typer.Typer`; `podcleaner_editor.cli.main() -> None`; `class EditorError(Exception)` whose message `main()` prints as `Error: <message>` on stderr, then exits with code 2.

- [ ] **Step 1:** install uv (`brew install uv`), `uv init --package --python 3.12` without overwriting the existing files. `pyproject.toml` modelled on podcleaner-clips: `name = "podcleaner-editor"`, `license = "MIT"`, `authors = [{ name = "Julien Gaudet" }]`, `requires-python = ">=3.11,<3.13"`, scripts `podcleaner-editor = "podcleaner_editor.cli:main"` and `pedit = "podcleaner_editor.cli:main"`, dependencies `typer`, `rich`, `platformdirs`, `numpy`, `soundfile`, `silero-vad`, `onnxruntime`; dev group `pytest`, `ruff`; build backend `uv_build`. Ruff: `line-length = 100`, `target-version = "py311"`, `extend-exclude = ["docs"]`, rules `E,F,I,UP,B`, isort `known-first-party = ["podcleaner_editor"]`. pytest: `testpaths = ["tests"]`, `markers = ["slow: loads a model"]`, `addopts = "-m 'not slow'"`.
- [ ] **Step 2: failing tests**

```python
def test_version_command_prints_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0 and "0.1.0" in result.output

def test_version_option():
    assert "0.1.0" in CliRunner().invoke(app, ["--version"]).output

def test_command_alone_prints_help():
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0 and "run" in result.output

def test_editor_error_exits_2_with_message(monkeypatch, capsys):
    # main() on a command that raises EditorError("File not found: x.wav")
    # → SystemExit(2), "Error: File not found: x.wav" on stderr, no "Traceback"
```

- [ ] **Step 3:** `uv run pytest` → FAIL (module missing).
- [ ] **Step 4:** implement `cli.py`: the `version` command and `--version` option, help when the command is called alone (`invoke_without_command=True`), and `main()` that catches `EditorError`.
- [ ] **Step 5:** `uv run pytest` → PASS. Edit a `.py` file and check that the hook (`.claude/hooks/python_checks.py`, already the podcleaner-clips version) runs Ruff and pytest through `uv run`.
- [ ] **Step 6:** CI: copy `ci.yml` from podcleaner-clips (macOS + Windows, Python 3.11 and 3.12, ffmpeg through brew/choco, `uv sync --locked`, `ruff check`, `ruff format --check`, `pytest`). graphify: copy from podcleaner-clips the `PreToolUse` / `SessionStart` hooks of `.claude/settings.json`, `.claude/skills/graphify/`, the `graphify-out/` entries of `.gitignore` and the "Working with Claude Code (graphify)" section of both CONTRIBUTING files; run `graphify update .`.
- [ ] **Step 7:** commit `chore: project scaffold, minimal CLI, CI / socle du projet, CLI minimale, CI`.

---

### Task 2: intervals and timecodes

**Files:** Create `src/podcleaner_editor/timeline.py`, `tests/test_timeline.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, order=True) class Interval: start: float; end: float` (seconds; `ValueError` if `end < start`); `duration` property.
  - `merge(intervals: Iterable[Interval], max_gap: float = 0.0) -> list[Interval]`: sorts, and merges those separated by ≤ `max_gap`.
  - `union(*lists: Iterable[Interval]) -> list[Interval]`
  - `intersect(a: list[Interval], b: list[Interval]) -> list[Interval]`
  - `invert(intervals: list[Interval], total: float) -> list[Interval]`: the gaps within `[0, total]`.
  - `format_tc(seconds: float) -> str`

- [ ] **Step 1: failing tests**

```python
def test_merge_joins_close_intervals():
    assert merge([I(0, 1), I(1.2, 2), I(5, 6)], max_gap=0.3) == [I(0, 2), I(5, 6)]

def test_union_and_intersect():
    assert union([I(0, 2)], [I(1, 3)]) == [I(0, 3)]
    assert intersect([I(0, 2), I(4, 6)], [I(1, 5)]) == [I(1, 2), I(4, 5)]

def test_invert_returns_gaps_within_total():
    assert invert([I(1, 2), I(3, 4)], total=5) == [I(0, 1), I(2, 3), I(4, 5)]
    assert invert([], total=5) == [I(0, 5)]

def test_format_tc():
    assert format_tc(0) == "00:00:00.000"
    assert format_tc(7803.4567) == "02:10:03.457"

def test_interval_rejects_negative_duration():
    with pytest.raises(ValueError): I(2, 1)
```

- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(timeline): intervals and timecodes / intervalles et timecodes`.

---

### Task 3: settings and configuration file

**Files:** Create `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Layout = Literal["separate", "mixed"]`
  - `@dataclass(frozen=True) class Settings`, fields and defaults, grouped by the TOML section they are read from:

| TOML key | Field | Default | Source |
| --- | --- | --- | --- |
| `[paths] output_dir` | `output_dir: Path \| None` | `None` | spec (per-person file) |
| `[recording] layout` | `layout: Layout` | `"separate"` | spec |
| `[recording] speakers` | `speakers: tuple[str, str]` | `("Voice A", "Voice B")` | choice |
| `[silences] min_s` | `silence_min_s` | 1.0 | spec |
| `[silences] target_s` | `silence_target_s` | 0.4 | spec |
| `[silences] fade_ms` | `fade_ms` | 30 | choice (used in M3) |
| `[vad] threshold` | `vad_threshold` | 0.5 | Silero default |
| `[vad] min_speech_ms` | `vad_min_speech_ms` | 250 | Silero default |
| `[vad] min_silence_ms` | `vad_min_silence_ms` | 100 | Silero default |
| `[levels] hop_s` | `level_hop_s` | 0.01 | choice |
| `[levels] bleed_margin_db` | `bleed_margin_db` | 10.0 | Review Focus 1 |
| `[levels] above_floor_db` | `activity_above_floor_db` | 12.0 | Review Focus 2 |
| `[film] threshold_dbfs` | `film_threshold_dbfs` | -45.0 | choice, to tune on an episode |
| `[film] merge_gap_s` | `film_merge_gap_s` | 2.0 | choice |
| `[film] min_clip_s` | `film_min_clip_s` | 3.0 | choice |
| `[overlaps] min_s` | `overlap_min_s` | 0.4 | choice |
| `[overlaps] floor_hold_s` | `overlap_floor_hold_s` | 1.0 | choice |
| `[overlaps] merge_gap_s` | `overlap_merge_gap_s` | 0.3 | choice |
| `[episode] max_duration_mismatch_s` | `max_duration_mismatch_s` | 2.0 | Review Focus 4 |
| `[claude] enabled` | `claude_enabled` | `True` | spec (used in M5) |
| `[claude] model` | `claude_model` | `"claude-sonnet-5-5"` | same as podcleaner-clips |

  - `CONFIG_ENV_VAR = "PODCLEANER_EDITOR_CONFIG"`
  - `resolve_config_path(cli_path: Path | None) -> Path`: `--config`, else the environment variable, else `platformdirs.user_config_dir("podcleaner-editor") / "config.toml"`.
  - `load_settings(path: Path) -> Settings`: missing file → defaults; replaces only the keys present.
  - `settings_values(s: Settings) -> dict[str, Any]` and `render_template(values: dict[str, Any]) -> str`: the commented TOML file (one English comment line above each key), written by `init`.

- [ ] **Step 1: failing tests**: `test_defaults_match_spec` (`silence_min_s == 1.0`, `silence_target_s == 0.4`, `layout == "separate"`); `test_toml_overrides_only_given_keys` (`[silences] target_s = 0.5` → 0.5, the rest at default); `test_unknown_key_raises` → `EditorError` naming `[section] key`; `test_bad_layout_raises` (`layout = "stereo"` → `EditorError` listing `separate`, `mixed`); `test_config_path_precedence` (option > environment variable > user folder); `test_template_round_trips` (`load_settings` of `render_template(settings_values(s))` gives `s` back).
- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(config): settings and configuration file / réglages et fichier de configuration`.

---

### Task 4: reading the tracks and the episode

**Files:** Create `src/podcleaner_editor/audio_io.py`, `src/podcleaner_editor/episode.py`, `tests/test_audio_io.py`, `tests/test_episode.py`, `tests/conftest.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class AudioInfo: path: Path; duration: float; sample_rate: int; channels: int; codec: str`
  - `probe(path: Path) -> AudioInfo` (ffprobe, JSON output)
  - `decode_mono_16k(path: Path) -> np.ndarray`: float32, mono (channel average), 16,000 Hz, via `ffmpeg -i … -ac 1 -ar 16000 -f f32le -` read from the pipe.
  - `frame_levels(samples: np.ndarray, sr: int, hop_s: float) -> np.ndarray`: RMS level in dBFS per `hop_s` frame, floor -120.
  - `require_ffmpeg() -> None`: `EditorError` if `ffmpeg` or `ffprobe` is missing (`shutil.which`).
  - `@dataclass(frozen=True) class Track: label: str; info: AudioInfo`
  - `@dataclass(frozen=True) class Episode: name: str; voices: tuple[Track, ...]; film: Track`; `layout` property (`"separate"` with 2 voices, `"mixed"` with 1); `duration` property = the shortest track.
  - `load_episode(voices: Sequence[Path], film: Path, name: str, settings: Settings) -> Episode`. Labels: `settings.speakers[i]` for 2 voices, `" + ".join(settings.speakers)` for a mixed track, `"Film"` for the film.
- `conftest.py` fixture: `make_wav(path, seconds, sr=48000, channels=1, subtype="PCM_24", signal="silence"|"tone")` with soundfile.

- [ ] **Step 1: failing tests**

```python
def test_decode_returns_mono_16k_float32(make_wav, tmp_path):
    p = make_wav(tmp_path / "a.wav", seconds=2, sr=48000, channels=2)
    x = decode_mono_16k(p)
    assert x.dtype == np.float32 and x.ndim == 1 and abs(len(x) - 32000) <= 160

def test_frame_levels_of_full_scale_sine_is_about_minus_3_dbfs(): ...  # ±0.5 dB
def test_frame_levels_of_silence_is_floor(): ...  # == -120

def test_load_episode_accepts_spaces_accents_float32_and_stereo(make_wav, tmp_path):
    d = tmp_path / "Épisode 12 été"
    # voice A PCM_24 mono, voice B FLOAT stereo, film 44.1 kHz → layout "separate", labels from speakers

def test_one_voice_file_is_mixed_layout(make_wav, tmp_path): ...   # stereo voices + film → layout "mixed", 1 voice
def test_zero_or_three_voices_rejected(): ...              # EditorError "1 or 2 voice files"
def test_load_episode_rejects_non_wav(tmp_path): ...       # .mp3 → EditorError "WAV only"
def test_load_episode_rejects_duration_mismatch(): ...     # 10 s vs 13 s → EditorError with both durations
def test_load_episode_missing_file(): ...                  # EditorError naming the path
def test_require_ffmpeg_missing(monkeypatch): ...          # shutil.which → None; message contains "ffmpeg" and "install"
```

- [ ] **Steps 2–4:** FAIL → implement → PASS. The format is checked with `probe(...).codec` starting with `pcm_` (not on the extension alone).
- [ ] **Step 5:** commit `feat(episode): read WAV tracks in both layouts / lire les pistes WAV dans les deux formes`.

---

### Task 5: speech detection and each voice's own activity

**Files:** Create `src/podcleaner_editor/analysis/__init__.py`, `analysis/vad.py`, `analysis/activity.py`, `tests/test_activity.py`, `tests/test_vad.py`, `tests/data/speech_*.wav` + `tests/data/ATTRIBUTION.md`

**Interfaces:**
- Consumes: `Interval`, `merge`, `intersect` (task 2); `Settings` (task 3); `frame_levels` (task 4).
- Produces:
  - `speech_intervals(samples: np.ndarray, settings: Settings) -> list[Interval]`: Silero (`load_silero_vad(onnx=True)` loaded once, `get_speech_timestamps(..., sampling_rate=16000, return_seconds=True)`), with `vad_threshold`, `vad_min_speech_ms`, `vad_min_silence_ms`.
  - `own_speech(vad: list[Interval], levels: np.ndarray, other_levels: np.ndarray, hop_s: float, bleed_margin_db: float) -> list[Interval]`: keeps the `vad` frames where `levels > other_levels - bleed_margin_db`, grouped into intervals. Not used in the mixed layout.
  - `noise_floor_db(levels: np.ndarray) -> float`: 10th percentile.
  - `loud_intervals(levels: np.ndarray, hop_s: float, threshold_db: float) -> list[Interval]`

- [ ] **Step 1: failing fast tests** (`test_activity.py`, synthetic levels, `hop_s=0.01`)

```python
def test_bleed_is_not_own_speech():
    # A talks alone at -20 dBFS from 0 to 5 s; B picks up the bleed at -38 dBFS; B's VAD says "speech" 0–5 s
    assert own_speech(vad_b, lv_b, lv_a, 0.01, 10.0) == []

def test_real_overlap_is_own_speech_on_both():
    # A and B at -20 dBFS from 2 to 3 s → B's own_speech == [I(2, 3)] (± one frame)

def test_noise_floor_and_loud_intervals():
    # noise at -60 dBFS, a laugh at -30 dBFS from 4 to 5.5 s → noise_floor_db ≈ -60,
    # loud_intervals(threshold = floor + 12) == [I(4, 5.5)]
```

- [ ] **Step 2: slow test** (`@pytest.mark.slow`): two LibriSpeech dev-clean excerpts (CC BY 4.0) of ~5 s, 16 kHz mono, joined with 3 s of silence; `speech_intervals` returns 2 intervals and neither overlaps the silence in the middle. Attribution in `tests/data/ATTRIBUTION.md`.
- [ ] **Steps 3–5:** FAIL → implement → `uv run pytest` and `uv run pytest -m slow` → PASS.
- [ ] **Step 6:** commit `feat(analysis): per-track VAD and bleed filter / VAD par piste et filtre de repisse`.

---

### Task 6: film clips

**Files:** Create `src/podcleaner_editor/analysis/film.py`, `tests/test_film.py`

**Interfaces:**
- Produces:
  - `film_activity(levels: np.ndarray, hop_s: float, threshold_dbfs: float) -> list[Interval]` (raw, used for silences)
  - `film_clips(activity: list[Interval], merge_gap_s: float, min_clip_s: float) -> list[Interval]` (used for events)

- [ ] **Step 1: failing tests**: `test_clip_with_short_pause_is_one_clip` (active 10–40 s and 41.5–70 s → `[I(10, 70)]`); `test_short_blip_is_ignored` (active 100–101 s → no clip); `test_two_clips_far_apart` (→ two clips).
- [ ] **Steps 2–4:** FAIL → implement (`loud_intervals`, then `merge`, then the duration filter) → PASS. **Step 5:** commit `feat(analysis): film clip detection / repérage des extraits de film`.

---

### Task 7: silences and the cut map

**Files:** Create `src/podcleaner_editor/cutmap.py`, `src/podcleaner_editor/detect/__init__.py`, `detect/silences.py`, `tests/test_cutmap.py`, `tests/test_silences.py`

**Interfaces:**
- Consumes: `Interval`, `union`, `invert`.
- Produces:
  - `find_silence_cuts(activities: list[list[Interval]], total: float, settings: Settings) -> list[Interval]`: takes the union of all activities (voices, loud sounds on the voices, film), keeps the gaps > `silence_min_s`, and returns for each one the part to remove, `Interval(gap.start + k, gap.end - k)` with `k = silence_target_s / 2`. A gap touching 0 or `total` is handled the same way.
  - `@dataclass(frozen=True) class CutMap: cuts: tuple[Interval, ...]` (sorted, disjoint, checked at construction)
    - `to_final(t: float) -> float`: `t` minus the duration cut before `t`; a `t` inside a cut gives the start of that cut on the final audio.
    - `final_duration(total: float) -> float`
    - `removed() -> float`

- [ ] **Step 1: failing tests**

```python
def test_long_silence_shortened_to_target():
    cuts = find_silence_cuts([[I(0, 10)], [I(13, 20)]], total=20, settings=S())
    assert cuts == [I(10.2, 12.8)]          # 3 s gap → 0.4 s kept

def test_silence_of_exactly_one_second_is_kept():
    assert find_silence_cuts([[I(0, 10), I(11, 20)]], 20, S()) == []

def test_laugh_on_one_track_prevents_cut():
    # voice A: speech 0–10 and 15–20; loud sounds on A (laugh) 11–13 → cuts [I(10.2, 10.8), I(13.2, 14.8)]

def test_film_activity_prevents_cut(): ...

def test_cutmap_to_final():
    m = CutMap((I(10, 12), I(20, 25)))
    assert m.to_final(5) == 5 and m.to_final(15) == 13 and m.to_final(30) == 23
    assert m.to_final(11) == 10 and m.final_duration(40) == 33

def test_cutmap_rejects_overlapping_cuts(): ...
```

- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(silences): shorten silences and build the cut map / raccourcir les blancs et construire la carte des coupes`.

---

### Task 8: events and attempts to take the floor

**Files:** Create `src/podcleaner_editor/events.py`, `src/podcleaner_editor/detect/overlaps.py`, `tests/test_overlaps.py`

**Interfaces:**
- Consumes: `Interval`, `merge`, `intersect`.
- Produces:
  - `class EventType(StrEnum)`: `CUT_REQUEST = "Requested cut"`, `CLIP_TO_ADD = "Clip to add"`, `FILM_CLIP = "Film clip"`, `OVERLAP = "Overlap"`, `SUGGESTION = "Suggestion"`. (`CUT_REQUEST`, `CLIP_TO_ADD` and `SUGGESTION` are filled in M2 and M5.)
  - `@dataclass(frozen=True) class Event: type: EventType; start: float; end: float; track: str; reason: str; source: Literal["rule", "claude"] = "rule"`
  - `find_overlap_attempts(a: list[Interval], b: list[Interval], label_a: str, label_b: str, settings: Settings) -> list[Event]`.
  Rule, applied both ways: a segment `s` of B is flagged if (1) it starts after the start of the merged A segment that covers it, (2) its overlap with A lasts ≥ `overlap_min_s`, (3) A, merged with `overlap_merge_gap_s`, still covers `[s.end, s.end + overlap_floor_hold_s]`. The event has `track=label_b` and the reason `"<B> tries to speak while <A> is speaking; <A> keeps the floor"`.

- [ ] **Step 1: failing tests**: `test_attempt_flagged` (A 0–20, B 5–6 → one event 5–6, track B); `test_short_backchannel_ignored` (B 5–5.3); `test_turn_taking_not_flagged` (A 0–10, B 9.5–20: A stops); `test_symmetric` (A interrupts B → track A); `test_brief_pause_in_a_still_counts_as_holding_floor` (A 0–6 and 6.2–20, B 5–6).
- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(overlaps): detect attempts to take the floor / repérer les tentatives de prise de parole`.

---

### Task 9: edit file

**Files:** Create `src/podcleaner_editor/report/__init__.py`, `report/markdown.py`, `tests/test_markdown.py`

**Interfaces:**
- Consumes: `Event`, `EventType` (task 8); `Episode` (task 4); `CutMap` (task 7); `format_tc` (task 2).
- Produces:
  - `@dataclass(frozen=True) class AnalysisResult: episode: Episode; events: list[Event]; silence_cuts: CutMap; dry_run: bool`
  - `render_edit_file(result: AnalysisResult, version: str, generated_on: date) -> str`

Exact format (headings and columns):

```markdown
# <episode.name>: edit file

Generated by podcleaner-editor <version> on <YYYY-MM-DD> · mode: <dry run|edit> · layout: <separate tracks|mixed voices>

## Timecodes

| # | Type | Track | Original | Final | Duration | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Film clip | Film | 00:12:03.120 | 00:11:58.320 | 00:01:22.000 | Activity on the film track |

## Report

### Tracks

| Track | File | Duration | Sample rate | Channels |

### Silences

<n> silences shortened, <removed duration> removed. Final duration: <HH:MM:SS.mmm> (original: <HH:MM:SS.mmm>).

### Overlaps

<n> attempts to take the floor flagged.        ← separate layout
Not available: both voices are on one track.   ← mixed layout

### Claude's opinions

None: processed without Claude.
```

  Events sorted by `start`; "Final" = `silence_cuts.to_final(start)`; no table rows → the line `_No events._` instead of the table; `|` characters in a reason escaped as `\|`.

- [ ] **Step 1: failing tests**: `test_render_matches_expected_snippet` (fake episode, one film clip and one overlap, one silence cut before both → expected Original and Final columns, chronological order); `test_empty_events_line`; `test_pipe_in_reason_is_escaped`; `test_report_counts_silences`; `test_mixed_layout_says_overlaps_not_available`.
- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(report): Markdown edit file / fichier de montage Markdown`.

---

### Task 10: analysis pipeline and the `run --dry-run` command

**Files:** Create `src/podcleaner_editor/pipeline.py`, `tests/test_pipeline.py`; Modify `src/podcleaner_editor/cli.py`, `README.md`, `README.fr.md`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `analyze(episode: Episode, settings: Settings, *, decode=decode_mono_16k, vad=speech_intervals, progress: Callable[[str], None] = lambda _: None) -> AnalysisResult` (`decode` and `vad` injectable for tests).
    - Separate layout: decode the 3 tracks → levels → VAD on both voices → cross `own_speech` → `loud_intervals` per voice (floor + `activity_above_floor_db`) → `film_activity` / `film_clips` → `find_silence_cuts` on `[own_a, own_b, loud_a, loud_b, film_activity]` → `find_overlap_attempts` → `FILM_CLIP` events (reason `"Activity on the film track"`) + `OVERLAP`.
    - Mixed layout: the voices track's raw VAD and `loud_intervals` (no `own_speech`), silences on `[vad, loud, film_activity]`, no overlap detection, `FILM_CLIP` events.
  - `run(...) -> Path`: writes `<out>/<name>.edit.md` and returns its path.
  - CLI: `pedit run --voice PATH [--voice PATH] --film PATH [--out DIR] [--name TEXT] [--config FILE] [--dry-run]`. One `--voice` = mixed layout, two = separate; if this disagrees with `[recording] layout`, the files win and a `⚠` notice says so. `--name` defaults to the `--out` folder name; without `--out`, `--name` is required and the output goes to `<output_dir>/<name>` (`EditorError` if `output_dir` is not set either: "run `pedit init` or pass --out"). Without `--dry-run`, M1 exits with `EditorError("Writing the edited audio comes in a later version; run again with --dry-run.")`. Prints one line per step (`Decoding…`, `Detecting speech…`, …) and the path of the written file.

- [ ] **Step 1: failing tests**: `test_analyze_with_fake_vad` (synthetic WAVs via `make_wav`: a tone on the film 30–60 s, a fake VAD returning fixed intervals → one `FILM_CLIP` 30–60 s, the expected silence cuts); `test_analyze_mixed_layout` (one voice file → no `OVERLAP` event, the same silence cuts as the union of the fake VAD); `test_cli_dry_run_writes_md` (CliRunner, fake `vad` via monkeypatch → `.md` file present, no `.wav` written in `--out`); `test_cli_without_dry_run_exits_2`; `test_cli_needs_out_or_output_dir`.
- [ ] **Step 2: slow test**: a 20 s episode built from `tests/data/speech_*.wav` on both voices and a tone on the film → the command succeeds and the `.md` contains `Film clip`; same with one mixed voice file.
- [ ] **Steps 3–5:** FAIL → implement → `uv run pytest` then `uv run pytest -m slow` → PASS.
- [ ] **Step 6:** `README.md` and `README.fr.md`: installation (`uv tool install …`, ffmpeg on macOS through Homebrew, on Windows through winget), example `--dry-run` commands in both layouts.
- [ ] **Step 7: check on a real episode** (manual, with Julien): run on a raw episode from `samples/`, note the processing time and read the `.md`: film clips in the right place, plausible overlaps, a sensible number of silences. Adjust the `Settings` defaults that miss, and record the values kept in `CLAUDE.md`.
- [ ] **Step 8:** commit `feat(cli): end-to-end run --dry-run command / commande run --dry-run de bout en bout`.

---

### Task 11: banner, `init` wizard and `config` command

**Files:** Create `src/podcleaner_editor/banner.py`, `src/podcleaner_editor/wizard.py`, `src/podcleaner_editor/claude_cli.py`, `tests/test_banner.py`, `tests/test_wizard.py`, `tests/test_claude_cli.py`; Modify `src/podcleaner_editor/cli.py`, `README.md`, `README.fr.md`

**Interfaces:**
- Consumes: `Settings`, `resolve_config_path`, `load_settings`, `settings_values`, `render_template` (task 3).
- Produces:
  - `banner.py`, adapted from podcleaner-clips: `NAME = "podcleaner-editor"`, `TAGLINE = "edit the episode, keep the timecodes"`, `NO_BANNER_ENV_VAR = "PODCLEANER_EDITOR_NO_BANNER"`, `RUST = "#94380c"`, `CREAM = "#fbf2f1"`; `pixel_lines(text: str = NAME) -> list[str]` (same 3×5 font, plus `"t": ("###", ".#.", ".#.", ".#.", ".#.")`); `wanted(ctx) -> bool`; `show(ctx) -> None`. Shown at the start of `init`, `run` and the command alone; root option `--no-banner`.
  - `claude_cli.py`, adapted from podcleaner-clips `claude.py`: `find_cli() -> str | None` (PATH, then `~/.local/bin`, `~/.claude/local`) and `cli_logged_in(cli: str, runner=...) -> bool | None` (`claude auth status --json`, key `loggedIn`). No `anthropic` import.
  - `wizard.py`: `run_wizard(path: Path, *, ask: bool) -> Path`. Questions, in this order, current values as defaults:
    1. Output folder (one subfolder per episode); created after confirmation if missing. Pasted or dragged paths are cleaned (quotes, macOS `\ ` escapes), as in podcleaner-clips `clean_path`.
    2. Recording layout: `separate` (one file per voice) or `mixed` (one stereo file with both voices).
    3. First names of the two voices.
    4. Use Claude when available? If `find_cli()` finds nothing or `cli_logged_in` is `False`, say so first ("Claude Code is not installed / not logged in (run: claude auth login)"); the answer is stored either way.
    Then: confirmation before replacing an existing file, atomic write (temporary file then `os.replace`), and the printed path. `ask=False` (outside a terminal or `--no-input`) writes the commented template with the defaults.
  - CLI: `pedit init [--no-input] [--config FILE]`; `pedit config [--path] [--config FILE]` prints the file path and each `key = value`.

- [ ] **Step 1: failing tests**

```python
def test_pixel_lines_have_the_same_width():
    lines = pixel_lines()
    assert len(lines) == 4 and len({len(l) for l in lines}) == 1

def test_banner_hidden_outside_a_terminal(capsys): ...        # stdout not a tty → nothing printed
def test_banner_hidden_by_env_var(monkeypatch): ...           # PODCLEANER_EDITOR_NO_BANNER=1
def test_banner_falls_back_to_one_line_when_narrow(): ...     # 40 columns → "podcleaner-editor 0.1.0 - …"

def test_wizard_writes_answers(tmp_path):
    # CliRunner input: "<out dir>\nmixed\nJulien\nMarc\ny\n" → load_settings(file).layout == "mixed",
    # speakers == ("Julien", "Marc"), output_dir == the folder
def test_wizard_offers_current_values(tmp_path): ...          # existing file + empty answers → same values
def test_wizard_keeps_file_when_replace_refused(tmp_path): ...
def test_init_no_input_writes_template(tmp_path): ...         # no question, file == render_template(defaults)
def test_wizard_warns_when_claude_code_is_missing(monkeypatch): ...  # find_cli → None → message shown
def test_clean_path_strips_quotes_and_escapes(): ...
def test_cli_logged_in_reads_json(): ...                      # fake runner → True / False / None on bad JSON
def test_config_path_option(tmp_path): ...                    # `pedit config --path` prints only the path
```

- [ ] **Steps 2–4:** FAIL → implement → PASS. Check by hand in a real terminal: `uv run pedit`, `uv run pedit init`, and narrow the window to see the one-line title.
- [ ] **Step 5:** README: a "Configure" section (`pedit init`, `pedit config`) in both languages.
- [ ] **Step 6:** commit `feat(cli): pixel-art banner, init wizard and config command / bannière pixel art, assistant init et commande config`.
