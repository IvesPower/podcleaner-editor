# M1: foundations and analysis, implementation plan

*[Version française](2026-11-05-m1-foundations-analysis.fr.md)*

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a `podcleaner run … --dry-run` CLI that reads an episode's two voice tracks and its film track, detects silences, overlaps and film clips, and writes the `.md` edit file with timecodes on the original audio and on the expected final audio.

**Architecture:** Python package `src/podcleaner/`. Input/output (ffmpeg, Silero VAD, files) stays at the edges; all detection is pure functions over lists of `Interval`, testable without audio. Analysis runs on a 16 kHz mono float32 copy of each track, decoded by ffmpeg, never on the full-resolution audio.

**Tech Stack:** Python 3.11–3.12, uv, Typer, numpy, soundfile, silero-vad (ONNX), ffmpeg/ffprobe (on PATH), pytest, Ruff.

**Spec:** [`docs/spec.md`](../../spec.md) · roadmap: [`2026-11-05-roadmap.md`](2026-11-05-roadmap.md)

## Global Constraints

- Runs on macOS and Windows; paths via `pathlib`, text files written with `encoding="utf-8"`.
- No account or API key required; M1 calls no network service at runtime.
- Input: WAV only; always 2 voice tracks + 1 film track.
- All analysis runs on the original audio; the cut map maps every timecode onto the final audio.
- Silences: every silence > 1 s where all tracks are quiet is brought down to about 0.4 s.
- Overlaps: timecode only, no volume change.
- One `.md` file per episode: Timecodes part, then Report part.
- `--dry-run` writes the report and timecodes without writing audio.
- Code identifiers in English; user-facing messages and the edit file in French (the exact French strings below are part of the spec).
- Timecodes formatted `HH:MM:SS.mmm`.
- Fast tests (`pytest -m "not slow"`) use no model and no network; tests that load Silero are marked `slow`.
- Each task is done on its own branch and lands in `main` through a pull request; commit messages follow Conventional Commits, in English.
- Documentation in English (`name.md`) and French (`name.fr.md`): any doc that changes changes in both languages.

## Review Focus

1. **Mic bleed**: each mic picks up the other voice; without a filter, all speech becomes an overlap. A track only counts as active when its level is above the other voice's level minus `bleed_margin_db` (10 dB). Test in task 5.
2. **Laughs, breaths, "mmh"**: Silero does not always classify them as speech; they must not be shortened as silences. A silence also requires that no track is above its noise floor + 12 dB. Test in task 7.
3. **Tracks with different durations or sample rates** (recording started at different times): duration gap > 2 s → clear error; different sample rates are accepted. Test in task 4.
4. **Paths with spaces and accents, stereo / 24-bit / float 32 WAV**: must read without error. Test in task 4.
5. **ffmpeg missing from PATH**: French message saying what to install, exit code 2, no Python traceback. Test in task 4.

---

## Files

```
pyproject.toml, uv.lock, CLAUDE.md
.gitignore, README.md / README.fr.md   (already present: extended)
.github/workflows/ci.yml
.claude/hooks/python_checks.py         (modified: goes through uv run)
src/podcleaner/__init__.py             __version__
src/podcleaner/cli.py                  Typer app: version, run
src/podcleaner/errors.py               PodcleanerError (user message, exit code 2)
src/podcleaner/timeline.py             Interval and operations, format_tc
src/podcleaner/config.py               Settings + TOML loading
src/podcleaner/audio_io.py             probe, decode_mono_16k, frame_levels
src/podcleaner/episode.py              Episode, load_episode
src/podcleaner/analysis/vad.py         speech_intervals (Silero)
src/podcleaner/analysis/activity.py    own_speech, loud_intervals, noise_floor_db
src/podcleaner/analysis/film.py        film_activity, film_clips
src/podcleaner/detect/silences.py      find_silence_cuts
src/podcleaner/detect/overlaps.py      find_overlap_attempts
src/podcleaner/events.py               EventType, Event (task 8)
src/podcleaner/cutmap.py               CutMap
src/podcleaner/report/markdown.py      render_edit_file
src/podcleaner/pipeline.py             analyze, run
tests/…                                one test file per module, tests/data/ for speech
```

---

### Task 1: repository scaffold and minimal CLI

**Files:**
- Create: `pyproject.toml`, `CLAUDE.md`, `.github/workflows/ci.yml`, `src/podcleaner/__init__.py`, `src/podcleaner/cli.py`, `src/podcleaner/errors.py`, `tests/test_cli.py`
- Modify: `.claude/hooks/python_checks.py`

**Interfaces:**
- Produces: `podcleaner.__version__: str = "0.1.0"`; `podcleaner.cli.app: typer.Typer`; `class PodcleanerError(Exception)` whose message the CLI prints as is, then exits with code 2.

- [ ] **Step 1:** install uv (`brew install uv`), create a `chore/scaffold` branch, `uv init --package --python 3.12` (the repository, `.gitignore`, `LICENSE` and the READMEs already exist: do not overwrite them). `pyproject.toml`: `requires-python = ">=3.11,<3.13"`, script `podcleaner = "podcleaner.cli:app"`, dependencies `typer`, `numpy`, `soundfile`, `silero-vad`, `onnxruntime`; dev group `pytest`, `ruff`. Ruff: `line-length = 100`, rules `E,F,I,UP,B`. pytest: `markers = ["slow: loads a model"]`, `addopts = "-m 'not slow'"`.
- [ ] **Step 2:** check that `.gitignore` covers `.venv/`, `samples/`, `out/`, `*.wav` except `tests/data/*.wav` (already the case).
- [ ] **Step 3: failing test**

```python
def test_version_command_prints_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output

def test_podcleaner_error_exits_2_with_message(monkeypatch):
    # a command that raises PodcleanerError("Fichier introuvable : x.wav")
    # → exit_code == 2, the message is in the output, no "Traceback"
```

- [ ] **Step 4:** `uv run pytest` → FAIL (module missing).
- [ ] **Step 5:** implement `cli.py`: a `version` command, and an entry point that catches `PodcleanerError`, prints `Erreur : <message>` to stderr and exits with 2.
- [ ] **Step 6:** `uv run pytest` → PASS.
- [ ] **Step 7:** hook: if `uv.lock` exists at the root, run `uv run ruff …` and `uv run pytest -q -x -m "not slow"`; otherwise keep the current behaviour. Check by editing a `.py` file: the hook passes.
- [ ] **Step 8:** `CLAUDE.md`: list the spec's decisions ("Decisions" table, points to watch, outputs) + the commands `uv run pytest`, `uv run pytest -m slow`, `uv run ruff check`. CI: matrix `macos-latest`, `windows-latest`, Python 3.11 and 3.12, `astral-sh/setup-uv`, `FedericoCarboni/setup-ffmpeg`, then `uv run ruff check` and `uv run pytest`.
- [ ] **Step 9:** commit `chore: project scaffold, minimal CLI, CI`.

---

### Task 2: intervals and timecodes

**Files:** Create `src/podcleaner/timeline.py`, `tests/test_timeline.py`

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
- [ ] **Step 5:** commit `feat(timeline): intervals and timecodes`.

---

### Task 3: settings

**Files:** Create `src/podcleaner/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Settings` with these fields and defaults:

| Field | Default | Source |
| --- | --- | --- |
| `silence_min_s` | 1.0 | spec |
| `silence_target_s` | 0.4 | spec |
| `fade_ms` | 30 | choice (used in M3) |
| `vad_threshold` | 0.5 | Silero default |
| `vad_min_speech_ms` | 250 | Silero default |
| `vad_min_silence_ms` | 100 | Silero default |
| `level_hop_s` | 0.01 | choice |
| `bleed_margin_db` | 10.0 | Review Focus 1 |
| `activity_above_floor_db` | 12.0 | Review Focus 2 |
| `film_threshold_dbfs` | -45.0 | choice, to tune on an episode |
| `film_merge_gap_s` | 2.0 | choice |
| `film_min_clip_s` | 3.0 | choice |
| `overlap_min_s` | 0.4 | choice |
| `overlap_floor_hold_s` | 1.0 | choice |
| `overlap_merge_gap_s` | 0.3 | choice |
| `max_duration_mismatch_s` | 2.0 | Review Focus 3 |

  `load_settings(path: Path | None) -> Settings`: reads a TOML file (`tomllib`), `[podcleaner]` section, and replaces only the keys present.

- [ ] **Step 1: failing tests**: `test_defaults_match_spec` (`silence_min_s == 1.0`, `silence_target_s == 0.4`); `test_toml_overrides_only_given_keys` (file with `silence_target_s = 0.5` → 0.5, the rest at default); `test_unknown_key_raises` → `PodcleanerError` naming the key.
- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(config): settings and TOML loading`.

---

### Task 4: reading the tracks and the episode

**Files:** Create `src/podcleaner/audio_io.py`, `src/podcleaner/episode.py`, `tests/test_audio_io.py`, `tests/test_episode.py`, `tests/conftest.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class AudioInfo: path: Path; duration: float; sample_rate: int; channels: int; codec: str`
  - `probe(path: Path) -> AudioInfo` (ffprobe, JSON output)
  - `decode_mono_16k(path: Path) -> np.ndarray`: float32, mono (channel average), 16,000 Hz, via `ffmpeg -i … -ac 1 -ar 16000 -f f32le -` read from the pipe.
  - `frame_levels(samples: np.ndarray, sr: int, hop_s: float) -> np.ndarray`: RMS level in dBFS per `hop_s` frame, floor -120.
  - `require_ffmpeg() -> None`: `PodcleanerError` if `ffmpeg` or `ffprobe` is missing (`shutil.which`).
  - `@dataclass(frozen=True) class Track: label: str; info: AudioInfo`
  - `@dataclass(frozen=True) class Episode: name: str; voice_a: Track; voice_b: Track; film: Track`; `duration` property = the shortest of the three.
  - `load_episode(voice_a: Path, voice_b: Path, film: Path, name: str, settings: Settings) -> Episode`; `label` = file name without extension.
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
    # voice A PCM_24 mono, voice B FLOAT stereo, film 44.1 kHz → Episode loaded, labels = file names

def test_load_episode_rejects_non_wav(tmp_path): ...       # .mp3 → PodcleanerError "WAV uniquement"
def test_load_episode_rejects_duration_mismatch(): ...     # 10 s vs 13 s → PodcleanerError with both durations
def test_load_episode_missing_file(): ...                  # PodcleanerError naming the path
def test_require_ffmpeg_missing(monkeypatch): ...          # shutil.which → None; message contains "ffmpeg" and "installer"
```

- [ ] **Steps 2–4:** FAIL → implement → PASS. The format is checked with `probe(...).codec` starting with `pcm_` (not on the extension alone).
- [ ] **Step 5:** commit `feat(episode): read WAV tracks and validate the episode`.

---

### Task 5: speech detection and each voice's own activity

**Files:** Create `src/podcleaner/analysis/__init__.py`, `analysis/vad.py`, `analysis/activity.py`, `tests/test_activity.py`, `tests/test_vad.py`, `tests/data/speech_*.wav` + `tests/data/ATTRIBUTION.md`

**Interfaces:**
- Consumes: `Interval`, `merge`, `intersect` (task 2); `Settings` (task 3); `frame_levels` (task 4).
- Produces:
  - `speech_intervals(samples: np.ndarray, settings: Settings) -> list[Interval]`: Silero (`load_silero_vad(onnx=True)` loaded once, `get_speech_timestamps(..., sampling_rate=16000, return_seconds=True)`), with `vad_threshold`, `vad_min_speech_ms`, `vad_min_silence_ms`.
  - `own_speech(vad: list[Interval], levels: np.ndarray, other_levels: np.ndarray, hop_s: float, bleed_margin_db: float) -> list[Interval]`: keeps the `vad` frames where `levels > other_levels - bleed_margin_db`, grouped into intervals.
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
- [ ] **Step 6:** commit `feat(analysis): per-track VAD and bleed filter`.

---

### Task 6: film clips

**Files:** Create `src/podcleaner/analysis/film.py`, `tests/test_film.py`

**Interfaces:**
- Produces:
  - `film_activity(levels: np.ndarray, hop_s: float, threshold_dbfs: float) -> list[Interval]` (raw, used for silences)
  - `film_clips(activity: list[Interval], merge_gap_s: float, min_clip_s: float) -> list[Interval]` (used for events)

- [ ] **Step 1: failing tests**: `test_clip_with_short_pause_is_one_clip` (active 10–40 s and 41.5–70 s → `[I(10, 70)]`); `test_short_blip_is_ignored` (active 100–101 s → no clip); `test_two_clips_far_apart` (→ two clips).
- [ ] **Steps 2–4:** FAIL → implement (`loud_intervals`, then `merge`, then the duration filter) → PASS. **Step 5:** commit `feat(analysis): film clip detection`.

---

### Task 7: silences and the cut map

**Files:** Create `src/podcleaner/cutmap.py`, `src/podcleaner/detect/__init__.py`, `detect/silences.py`, `tests/test_cutmap.py`, `tests/test_silences.py`

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

- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(silences): shorten silences and build the cut map`.

---

### Task 8: events and attempts to take the floor

**Files:** Create `src/podcleaner/events.py`, `src/podcleaner/detect/overlaps.py`, `tests/test_overlaps.py`

**Interfaces:**
- Consumes: `Interval`, `merge`, `intersect`.
- Produces:
  - `class EventType(StrEnum)`: `CUT_REQUEST = "Coupe demandée"`, `CLIP_TO_ADD = "Extrait à ajouter"`, `FILM_CLIP = "Extrait de film"`, `OVERLAP = "Chevauchement"`, `SUGGESTION = "Suggestion"`. (`CUT_REQUEST`, `CLIP_TO_ADD` and `SUGGESTION` are filled in M2 and M5.)
  - `@dataclass(frozen=True) class Event: type: EventType; start: float; end: float; track: str; reason: str; source: Literal["règle", "claude"] = "règle"`
  - `find_overlap_attempts(a: list[Interval], b: list[Interval], label_a: str, label_b: str, settings: Settings) -> list[Event]`.
  Rule, applied both ways: a segment `s` of B is flagged if (1) it starts after the start of the merged A segment that covers it, (2) its overlap with A lasts ≥ `overlap_min_s`, (3) A, merged with `overlap_merge_gap_s`, still covers `[s.end, s.end + overlap_floor_hold_s]`. The event has `track=label_b` and the reason `"<B> tente de parler pendant que <A> parle ; <A> garde la parole"`.

- [ ] **Step 1: failing tests**: `test_attempt_flagged` (A 0–20, B 5–6 → one event 5–6, track B); `test_short_backchannel_ignored` (B 5–5.3); `test_turn_taking_not_flagged` (A 0–10, B 9.5–20: A stops); `test_symmetric` (A interrupts B → track A); `test_brief_pause_in_a_still_counts_as_holding_floor` (A 0–6 and 6.2–20, B 5–6).
- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(overlaps): detect attempts to take the floor`.

---

### Task 9: edit file

**Files:** Create `src/podcleaner/report/__init__.py`, `report/markdown.py`, `tests/test_markdown.py`

**Interfaces:**
- Consumes: `Event`, `EventType` (task 8); `Episode` (task 4); `CutMap` (task 7); `format_tc` (task 2).
- Produces:
  - `@dataclass(frozen=True) class AnalysisResult: episode: Episode; events: list[Event]; silence_cuts: CutMap; dry_run: bool`
  - `render_edit_file(result: AnalysisResult, version: str, generated_on: date) -> str`

Exact format (headings and columns; the edit file is in French):

```markdown
# <episode.name> : fichier de montage

Généré par podcleaner <version> le <AAAA-MM-JJ> · mode : <dry-run|montage>

## Timecodes

| # | Type | Piste | Original | Final | Durée | Raison |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Extrait de film | <label film> | 00:12:03.120 | 00:11:58.320 | 00:01:22.000 | Activité sur la piste film |

## Rapport

### Pistes

| Piste | Durée | Fréquence | Canaux |

### Blancs

<n> blancs raccourcis, <durée retirée> retirées. Durée finale : <HH:MM:SS.mmm> (originale : <HH:MM:SS.mmm>).

### Avis de Claude

Aucun : traitement sans clé d'API.
```

  Events sorted by `start`; "Final" = `silence_cuts.to_final(start)`; no table rows → the line `_Aucun événement._` instead of the table; `|` characters in a reason escaped as `\|`.

- [ ] **Step 1: failing tests**: `test_render_matches_expected_snippet` (fake episode, one film clip and one overlap, one silence cut before both → expected Original and Final columns, chronological order); `test_empty_events_line`; `test_pipe_in_reason_is_escaped`; `test_report_counts_silences`.
- [ ] **Steps 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(report): Markdown edit file`.

---

### Task 10: analysis pipeline and the `run --dry-run` command

**Files:** Create `src/podcleaner/pipeline.py`, `tests/test_pipeline.py`; Modify `src/podcleaner/cli.py`, `README.md`, `README.fr.md`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `analyze(episode: Episode, settings: Settings, *, decode=decode_mono_16k, vad=speech_intervals) -> AnalysisResult` (both functions injectable for tests). Order: decode the 3 tracks → levels → VAD on both voices → cross `own_speech` → `loud_intervals` per voice (floor + `activity_above_floor_db`) → `film_activity` / `film_clips` → `find_silence_cuts` on `[own_a, own_b, loud_a, loud_b, film_activity]` → `find_overlap_attempts` → `FILM_CLIP` events (reason `"Activité sur la piste film"`) + `OVERLAP`.
  - `run(...) -> Path`: writes `<out>/<name>.montage.md` and returns its path.
  - CLI: `podcleaner run --voice-a PATH --voice-b PATH --film PATH --out DIR [--name TEXT] [--config FILE] [--dry-run]`. `--name` defaults to the name of the `--out` folder. Without `--dry-run`, M1 exits with `PodcleanerError("Le montage audio arrive dans une prochaine version ; relancez avec --dry-run.")`. Prints one line per step (`Décodage…`, `Détection de parole…`, …) and the path of the written file.

- [ ] **Step 1: failing tests**: `test_analyze_with_fake_vad` (synthetic WAVs via `make_wav`: a tone on the film 30–60 s, a fake VAD returning fixed intervals → one `FILM_CLIP` 30–60 s, the expected silence cuts); `test_cli_dry_run_writes_md` (CliRunner, fake `vad` via monkeypatch → `.md` file present, no `.wav` written in `--out`); `test_cli_without_dry_run_exits_2`.
- [ ] **Step 2: slow test**: a 20 s episode built from `tests/data/speech_*.wav` on both voices and a tone on the film → the command succeeds and the `.md` contains `Extrait de film`.
- [ ] **Steps 3–5:** FAIL → implement → `uv run pytest` then `uv run pytest -m slow` → PASS.
- [ ] **Step 6:** `README.md` and `README.fr.md`: installation (uv, ffmpeg on macOS through Homebrew, on Windows through winget), an example `--dry-run` command.
- [ ] **Step 7: check on a real episode** (manual, with Julien): run on a raw episode from `samples/`, note the processing time and read the `.md`: film clips in the right place, plausible overlaps, a sensible number of silences. Adjust the `Settings` defaults that miss, and record the values kept in `CLAUDE.md`.
- [ ] **Step 8:** commit `feat(cli): end-to-end run --dry-run command`.
