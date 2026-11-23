# M2: transcription and markers, implementation plan

[Français](2026-11-22-m2-transcription-markers.fr.md) · **English**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pedit run … --dry-run` also transcribes each voice's active passages (word timestamps), finds the spoken instructions to Claude ("Dis Claude, on va couper ce passage-là."; first planned as fixed phrases such as "Claude ici on veut couper") and the "euh"s, decides which "euh"s and marker phrases can be cut, and writes all of it into the edit file, with final timecodes that already account for those cuts.

**Architecture:** transcription is an edge module (`analysis/transcribe.py`: mlx-whisper on Apple silicon, faster-whisper elsewhere, adapted from podcleaner-clips `transcribe.py`) behind a `Transcriber` protocol, so the pipeline can be tested with a fake one. Everything after it is pure functions over `Word` and `Interval` lists (`detect/fillers.py`, `detect/markers.py`). Each voice is transcribed on its own speech only (bleed filter from M1), and its words are cached in `<out>/<name>.words.json` so a second `--dry-run` with other settings does not transcribe again. Cuts of hesitations and marker phrases join the silence cuts in one cut map; the silences are computed after those cuts are taken out of the activity, so an "euh" between two pauses leaves one short pause, not a long one.

**Tech Stack:** M1's stack, plus `mlx-whisper` (macOS arm64) / `faster-whisper` (elsewhere), model `large-v3-turbo`, and `rapidfuzz`.

**Spec:** [`docs/spec.md`](../../spec.md) (translation of [`docs/spec.fr.md`](../../spec.fr.md), the reference) · roadmap: [`2026-11-05-roadmap.md`](2026-11-05-roadmap.md) · M1 plan: [`2026-11-05-m1-foundations-analysis.md`](2026-11-05-m1-foundations-analysis.md)

## Global Constraints

- All of M1's global constraints still hold (platforms, `pathlib`, UTF-8, English everywhere, `HH:MM:SS.mmm`, one branch and one PR per task, commit and PR titles `type(scope): English / français`, docs in both languages).
- Only active passages are transcribed, never the whole track; never the full-resolution audio in memory; at most one decoded voice track in memory during transcription.
- Without Claude, everything works with fixed rules; M2 makes no call to Claude.
- Rule for an "euh" (chosen by Julien on 22 Nov 2026, "wide"): every standalone hesitation word is cut, unless another word or the other voice's speech falls inside its cut window, or a film clip does, or it lasts more than `filler_max_s`; those are flagged, never cut. Claude (M5) will be able to undo a cut.
- Mixed layout: an "euh" is a cut candidate only if no other transcribed word overlaps the cut window (spec).
- Spoken markers: an explicit call to Claude at the start of a sentence ("dis Claude", or "Claude" followed by a comma or a pause; decided by Julien on 23 Nov 2026) followed by an instruction that holds an action word (rule changed by Julien on 22 Nov 2026 after the test recording, instead of fixed phrases) gives a `Requested cut` or `Clip to add` event in the Timecodes, and the instruction itself is cut from the audio (chosen by Julien on 22 Nov 2026), under the same "no other speech, no film" condition.
- Cuts are the same on every track: any cut (silence, "euh", marker) is blocked by speech on any other track.
- `--dry-run` still writes no audio; the words cache (JSON) is allowed.
- French text allowed in code and configuration only for speech to recognize: the marker trigger and action words, the filler words and the Whisper prompt.
- Fast tests load no model and use no network; tests that load Whisper are marked `slow` and skip when `samples/pedit` is absent.
- Model download on first run (~1.6 GB from Hugging Face) is announced in the progress line.

## Review Focus

1. **Whisper leaves out the "euh"s**: it tends to write clean speech. The prompt holds fillers (`"Euh, alors, euh… bon, hum, voilà."`) to make it write them. Test in task 2 (prompt passed to both backends); count checked on the test recording in task 7.
2. **The other voice's bleed transcribed on the wrong mic**: a marker or an "euh" would show up twice, on both tracks. Words whose middle is outside the track's own speech are dropped. Tests in tasks 2 and 7.
3. **An "euh" between two pauses**: `0.7 s pause + euh + 0.7 s pause` must not become a 1.4 s silence once the "euh" is cut. Silences are computed with the speech cuts taken out of the activity. Test in task 7.
4. **First run without network, or a model that does not load**: clear message (`Error: Could not load the Whisper model large-v3-turbo: …`), exit code 2, no traceback. Test in task 2.
5. **Stale or broken words cache**: a changed WAV, other transcription settings or a truncated JSON must lead to a new transcription, never to reusing the wrong words or a crash. Tests in task 3.

---

## Files

```
src/podcleaner_editor/config.py                 new settings (task 1)
src/podcleaner_editor/timeline.py               subtract (task 4)
src/podcleaner_editor/analysis/words.py         Word, normalize, speech_passages, keep_own_words
src/podcleaner_editor/analysis/transcribe.py    Transcriber, backends, make_transcriber, transcribe_passages
src/podcleaner_editor/analysis/words_cache.py   cache_key, load_words, save_words
src/podcleaner_editor/detect/cuts.py            cut_window, snap_to_quiet, blocking_reason
src/podcleaner_editor/detect/fillers.py         Filler, is_filler, find_fillers
src/podcleaner_editor/detect/markers.py         Marker, find_markers
src/podcleaner_editor/report/markdown.py        new sections
src/podcleaner_editor/pipeline.py               transcription step, speech cuts
tests/test_words.py, test_transcribe.py, test_words_cache.py, test_cuts.py,
tests/test_fillers.py, test_markers.py          + test_config, test_timeline, test_markdown, test_pipeline
```

---

### Task 1: settings and dependencies

**Files:**
- Modify: `pyproject.toml`, `uv.lock`, `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces new `Settings` fields (TOML section and key in brackets, template order as listed, after `[film]` and before `[overlaps]`):

| Field | Default | TOML | Template comment |
| --- | --- | --- | --- |
| `whisper_model: str` | `"large-v3-turbo"` | `[transcription] model` | Whisper model (mlx-community name on Apple silicon). |
| `transcription_language: str` | `"fr"` | `[transcription] language` | Language spoken in the episode. |
| `transcription_prompt: str` | `"Euh, alors, euh… bon, hum, voilà."` | `[transcription] prompt` | Example text that makes Whisper write the hesitations. |
| `passage_gap_s: float` | `1.0` | `[transcription] passage_gap_s` | Speech closer than this is transcribed in one passage (seconds). |
| `passage_pad_s: float` | `0.2` | `[transcription] passage_pad_s` | Margin added around each passage (seconds). |
| `filler_words: tuple[str, ...]` | `("euh", "heu", "euhm", "hum", "hm")` | `[hesitations] words` | Words counted as hesitations. |
| `filler_pad_s: float` | `0.05` | `[hesitations] pad_s` | Margin cut around a hesitation (seconds). |
| `filler_max_s: float` | `1.5` | `[hesitations] max_s` | Longer hesitations are flagged, not cut (seconds). |
| `filler_snap_s: float` | `0.08` | `[hesitations] snap_s` | How far a cut edge may move to the quietest point (seconds). |
| `marker_trigger: str` | `"claude"` | `[markers] trigger` | Word that opens a spoken instruction, at the start of a sentence. |
| `marker_cut_words: tuple[str, ...]` | `("couper", "coupe", "supprimer", "supprime", "enlever", "enleve", "retirer", "retire")` | `[markers] cut_words` | Words that make an instruction a cut. |
| `marker_clip_words: tuple[str, ...]` | `("ajouter", "ajoute", "extrait", "inserer", "insere")` | `[markers] clip_words` | Words that make an instruction a clip to add. |
| `marker_min_score: float` | `80.0` | `[markers] min_score` | Lowest similarity (0 to 100) for a heard word to count as the trigger. |
| `marker_pause_s: float` | `0.5` | `[markers] pause_s` | A pause this long starts or ends an instruction (seconds). |
| `marker_max_s: float` | `15.0` | `[markers] max_s` | Longest instruction (seconds). |
| `marker_pad_s: float` | `0.1` | `[markers] pad_s` | Margin cut around an instruction (seconds). |

- [ ] **Step 1:** dependencies: `"mlx-whisper ; sys_platform == 'darwin' and platform_machine == 'arm64'"`, `"faster-whisper ; sys_platform != 'darwin' or platform_machine != 'arm64'"`, `"rapidfuzz"`; `uv lock`.
- [ ] **Step 2: failing tests**

```python
def test_filler_words_read_from_toml(tmp_path):
    # [hesitations] words = ["euh", "bah"] → settings.filler_words == ("euh", "bah")
def test_filler_words_must_be_non_empty_strings(tmp_path):
    # words = [] → EditorError; words = ["euh", 3] → EditorError, message names "[hesitations] words"
def test_template_round_trips_new_settings(tmp_path):
    # load_settings(file written by render_template(settings_values(Settings()))) == Settings()
```

- [ ] **Step 3:** `uv run pytest tests/test_config.py` → FAIL.
- [ ] **Step 4:** add the fields and `_KEYS` entries; in `_convert`, a `tuple` default other than `speakers` takes a non-empty list of non-empty strings (`"{label} must list words, such as [\"euh\", \"heu\"]"`).
- [ ] **Step 5:** `uv run pytest` → PASS (including the M1 tests: the `_KEYS` assertion holds).
- [ ] **Step 6:** commit `feat(config): transcription, hesitation and marker settings / réglages de transcription, d'hésitations et de marqueurs`.

---

### Task 2: words, passages and transcription

**Files:**
- Create: `src/podcleaner_editor/analysis/words.py`, `src/podcleaner_editor/analysis/transcribe.py`, `tests/test_words.py`, `tests/test_transcribe.py`

**Interfaces:**
- Consumes: `Interval`, `merge`, `Settings`, `EditorError`, `ANALYSIS_RATE`.
- Produces:
  - `words.py`: `@dataclass(frozen=True) class Word: text: str; start: float; end: float` (seconds on the original audio) with property `span -> Interval`; `normalize(text: str) -> str` (lowercase, accents removed through NFKD, every non-alphanumeric character → space, spaces collapsed, stripped); `speech_passages(speech: list[Interval], total: float, gap_s: float, pad_s: float) -> list[Interval]` (merge with `gap_s`, widen by `pad_s`, clamp to `[0, total]`, merge again); `keep_own_words(words: list[Word], own: list[Interval], tolerance: float) -> list[Word]` (keeps a word whose middle is inside an `own` interval widened by `tolerance`).
  - `transcribe.py`: `class Transcriber(Protocol)`: `name: str`; `words(self, audio: np.ndarray, offset: float) -> list[Word]` (audio mono 16 kHz, times shifted by `offset`, sorted, empty texts dropped). `make_transcriber(settings: Settings) -> Transcriber` (mlx on darwin/arm64, faster-whisper otherwise; `name` such as `"mlx-whisper large-v3-turbo"`; the model loads on the first call). Both backends pass `language=settings.transcription_language`, `initial_prompt=settings.transcription_prompt`, `word_timestamps=True`, `condition_on_previous_text=False`; mlx repo `mlx-community/whisper-<model>` unless the name holds a `/`; faster-whisper `compute_type="int8"`. Any exception while importing or loading the model → `EditorError(f"Could not load the Whisper model {model}: {exc}")`. `transcribe_passages(samples: np.ndarray, passages: list[Interval], transcriber: Transcriber) -> list[Word]` (one call per passage with `offset = passage.start`, results joined and sorted). `@dataclass(frozen=True) class TranscriptionInfo: backend: str; speech_s: float; cached_tracks: int`.

- [ ] **Step 1: failing tests**

```python
def test_normalize_strips_case_accents_and_punctuation():
    assert normalize("Claude, ici… On VEUT couper !") == "claude ici on veut couper"
    assert normalize("Été") == "ete" and normalize("aujourd'hui") == "aujourd hui"

def test_speech_passages_merge_pad_and_clamp():
    assert speech_passages([I(0.1, 2), I(2.5, 4), I(8, 9.9)], total=10, gap_s=1.0, pad_s=0.2) \
        == [I(0, 4.2), I(7.8, 10)]

def test_keep_own_words_drops_bleed():
    words = [Word("oui", 1.0, 1.2), Word("non", 5.0, 5.2)]
    assert keep_own_words(words, [I(0.5, 2)], tolerance=0.2) == [words[0]]

def test_transcribe_passages_shifts_times(): ...   # fake transcriber, 2 passages → offsets 3.0 and 10.0, sorted words
def test_mlx_backend_passes_prompt_and_language(monkeypatch):
    # fake `mlx_whisper` module in sys.modules records the kwargs:
    # initial_prompt == Settings().transcription_prompt, language == "fr", word_timestamps is True
def test_faster_whisper_backend_passes_prompt_and_language(monkeypatch): ...   # same, fake faster_whisper.WhisperModel
def test_model_load_failure_is_an_editor_error(monkeypatch):
    # fake module whose transcribe raises OSError("offline") →
    # EditorError("Could not load the Whisper model large-v3-turbo: offline")
```

- [ ] **Step 2: slow test** `test_transcribes_french_speech` (skips without `samples/pedit`): the first 15 s of `pedit-full-piste-1-julien.wav` → at least 10 words, all with `0 <= start <= end <= 15`.
- [ ] **Steps 3–5:** FAIL → implement → `uv run pytest` and `uv run pytest -m slow tests/test_transcribe.py` → PASS.
- [ ] **Step 6:** commit `feat(transcribe): word-level transcription of active passages / transcription au mot des passages actifs`.

---

### Task 3: words cache

**Files:**
- Create: `src/podcleaner_editor/analysis/words_cache.py`, `tests/test_words_cache.py`

**Interfaces:**
- Consumes: `Word`, `Interval`, `Settings`.
- Produces: `cache_key(path: Path, passages: list[Interval], settings: Settings) -> dict` (file name, size, `st_mtime_ns`, `whisper_model`, `transcription_language`, `transcription_prompt`, and the passages rounded to the millisecond); `load_words(cache_path: Path, label: str, key: dict) -> list[Word] | None` (`None` when the file is missing, unreadable, not the expected JSON shape, or its key for `label` differs); `save_words(cache_path: Path, label: str, key: dict, words: list[Word]) -> None` (keeps the other tracks' entries, writes UTF-8 to a temporary file then `os.replace`). File shape: `{"version": 1, "tracks": {label: {"key": {...}, "words": [[text, start, end], ...]}}}`.

- [ ] **Step 1: failing tests**: `test_round_trip`; `test_two_tracks_in_one_file`; `test_changed_file_misses` (rewrite the WAV → `None`); `test_changed_prompt_misses`; `test_changed_passages_misses`; `test_truncated_json_misses` (file holding `{"version": 1, "tra` → `None`, no exception); `test_wrong_shape_misses` (`{"version": 1, "tracks": []}` → `None`).
- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** commit `feat(transcribe): cache the words of each track / garder en cache les mots de chaque piste`.

---

### Task 4: cut windows and hesitations

**Files:**
- Create: `src/podcleaner_editor/detect/cuts.py`, `src/podcleaner_editor/detect/fillers.py`, `tests/test_cuts.py`, `tests/test_fillers.py`
- Modify: `src/podcleaner_editor/timeline.py`, `tests/test_timeline.py`

**Interfaces:**
- Consumes: `Word`, `normalize`, `Interval`, `merge`, `intersect`, `invert`, `Settings`.
- Produces:
  - `timeline.subtract(a: list[Interval], b: list[Interval]) -> list[Interval]`: the moments of `a` not covered by `b`.
  - `cuts.py` (shared with task 5):
    - `cut_window(span: Interval, prev_end: float | None, next_start: float | None, pad: float) -> Interval`: `span` widened by `pad`, never past the end of the previous word or the start of the next one on the same track.
    - `snap_to_quiet(window: Interval, span: Interval, levels: np.ndarray, hop_s: float, snap_s: float, bounds: Interval) -> Interval`: each edge moves to the quietest frame within `snap_s` of it, staying outside `span` and inside `bounds` (the neighbours' limits).
    - `blocking_reason(window: Interval, other_speech: list[Interval], film: list[Interval]) -> str | None`: `"Other speech at the same time"` if `window` intersects `other_speech`, else `"During a film clip"` if it intersects `film`, else `None`.
  - `fillers.py`:
    - `@dataclass(frozen=True) class Filler: word: Word; track: str; context: str; cut: Interval | None; reason: str` (`cut` is `None` for a flagged one; `reason` is `"Isolated hesitation"` when cut).
    - `is_filler(text: str, words: tuple[str, ...]) -> bool`: `normalize(text)` is one token and, with repeated letters collapsed (`euuuh` → `euh`), equals one of `words` collapsed the same way.
    - `find_fillers(words: dict[str, list[Word]], other_speech: dict[str, list[Interval]], film: list[Interval], levels: dict[str, np.ndarray], settings: Settings) -> list[Filler]`, keyed by track label, sorted by time. For each filler word: if it lasts more than `filler_max_s` → flagged `"Too long to be sure it is a hesitation"`; if the previous word on the same track ends after it starts, or the next one starts before it ends → flagged `"Other speech at the same time"`; otherwise window = `snap_to_quiet(cut_window(...))`, and `blocking_reason(window, other_speech[track], film)` flags it or it is cut. `context`: up to 4 words before and 4 after, the filler in brackets (`"alors [euh] on a vu"`).

- [ ] **Step 1: failing tests**

```python
def test_subtract():
    assert subtract([I(0, 10)], [I(2, 3), I(5, 6)]) == [I(0, 2), I(3, 5), I(6, 10)]

def test_cut_window_stops_at_neighbours():
    assert cut_window(I(5.0, 5.4), prev_end=4.98, next_start=5.6, pad=0.05) == I(4.98, 5.45)

def test_snap_moves_edges_to_quiet_frames(): ...   # levels with a dip 0.06 s before the window start → start lands on it
def test_snap_never_enters_the_word(): ...
def test_blocking_reason_order(): ...               # both other speech and film → "Other speech at the same time"

def test_isolated_euh_is_cut():
    words = {"Julien": [Word("alors", 4.0, 4.6), Word("euh", 5.0, 5.4), Word("on", 5.8, 6.0)]}
    [f] = find_fillers(words, {"Julien": []}, [], {"Julien": quiet_levels}, SETTINGS)
    assert f.cut is not None and f.cut.start <= 5.0 and f.cut.end >= 5.4 and f.reason == "Isolated hesitation"
    assert f.context == "alors [euh] on"

def test_variants_count_as_fillers():
    assert is_filler("Euuuh…", SETTINGS.filler_words) and is_filler("Hum,", SETTINGS.filler_words)
    assert not is_filler("heureux", SETTINGS.filler_words) and not is_filler("euh bon", SETTINGS.filler_words)

def test_euh_under_the_other_voice_is_flagged(): ...      # other_speech covers 5.2–5.3 → cut None, "Other speech at the same time"
def test_euh_overlapping_a_word_on_the_same_track_is_flagged(): ...   # mixed layout: next word starts at 5.3
def test_euh_during_film_clip_is_flagged(): ...           # "During a film clip"
def test_long_euh_is_flagged(): ...                       # 2.0 s → "Too long to be sure it is a hesitation"
```

- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** commit `feat(hesitations): find the "euh"s and decide which can be cut / repérer les « euh » et choisir ceux à couper`.

---

### Task 5: spoken markers

**Files:**
- Create: `src/podcleaner_editor/detect/markers.py`, `tests/test_markers.py`

**Interfaces:**
- Consumes: `Word`, `normalize`, `word_cut_window`, `blocking_reason`, `OTHER_SPEECH` (task 4), `Event`, `EventType`, `Settings`, `rapidfuzz.fuzz.ratio`.
- Produces: `@dataclass(frozen=True) class Marker: event: Event; cut: Interval | None`; `find_markers(words: list[Word], track: str, other_speech: list[Interval], film: list[Interval], levels: np.ndarray, settings: Settings) -> list[Marker]`, sorted by time.
  Rule (changed by Julien on 22 Nov 2026 after the test recording, where he gives spoken instructions rather than fixed phrases; the first version matched `marker_cut_phrase` / `marker_clip_phrase` with fuzzy scores):
  - Trigger: a word whose first token (`normalize`) has `fuzz.ratio(token, marker_trigger) >= marker_min_score`. A word is at a sentence start when it is the track's first word, or the previous word ends with `.`, `?`, `!` or `…`, or the gap since the previous word is ≥ `marker_pause_s`; a hesitation or punctuation alone before it is looked through ("Euh, dis Claude").
  - Call (decided by Julien on 23 Nov 2026, so "Claude Chabrol a coupé…" or "je te le dis Claude, coupe" are not instructions): either the previous word is "dis" and "dis" is at a sentence start (then "dis" joins the instruction), or the trigger is at a sentence start and its word ends with `,` or is followed by a gap ≥ `marker_pause_s`.
  - The instruction runs from there to the first word after the trigger that ends a sentence or is followed by a gap ≥ `marker_pause_s`. It is at most `marker_max_s` long, measured from its first word ("dis" when present); one cut short there is kept in the audio (`cut = None`, reason ends `"; instruction kept: no clear end"`).
  - It is a marker only if it holds an action word: the first token found in `marker_cut_words` gives `CUT_REQUEST`, in `marker_clip_words` gives `CLIP_TO_ADD`.
  - Event: `start`/`end` = first and last word of the instruction, `track`, reason `'Spoken instruction: "<words as transcribed>"'`. Cut: `word_cut_window` with `marker_pad_s`; blocked (`cut = None`, reason ends `"; instruction kept: <reason>"`) by `blocking_reason`, or, as `"Other speech at the same time"`, by another word of the same track inside the window or two of the instruction's words overlapping (mixed layout).

- [ ] **Step 1: failing tests**

```python
def test_dis_claude_ajoute_is_a_clip_to_add(): ...        # "Dis Claude, ici il faudrait qu'on ajoute un passage de son…" → CLIP_TO_ADD
def test_dis_claude_on_va_couper_is_a_cut(): ...          # "dis Claude, on va couper ce passage-là, les dix dernières secondes." → CUT_REQUEST
def test_dis_claude_supprimer_is_a_cut(): ...             # "dis Claude, est-ce que tu peux supprimer la phrase juste avant…" → CUT_REQUEST
def test_spec_phrase_after_a_pause(): ...                 # pause, "Claude, ici on veut couper" → CUT_REQUEST
def test_claude_as_a_first_name_is_ignored(): ...        # "…film. Claude Chabrol a coupé…", "Bon. Claude Lelouch, dans cet extrait…" → []
def test_dis_mid_sentence_is_ignored(): ...              # "je te le dis Claude, coupe ça." → []
def test_claude_mid_sentence_is_ignored(): ...            # "j'ai demandé à Claude de couper ça." → []
def test_instruction_without_action_word_is_ignored(): ...  # "Bon. Claude, tu es là ?" → []
def test_misheard_trigger_still_found(): ...              # "Cloude" (score 83) → found; "Clode" (73) → []
def test_instruction_ends_at_a_pause(): ...
def test_instruction_capped_at_max_s(): ...
def test_two_instructions_in_a_row(): ...
def test_instruction_under_other_speech_is_kept_in_audio(): ...  # reason ends "; instruction kept: Other speech at the same time"
def test_instruction_during_a_film_clip_is_kept_in_audio(): ...
def test_mixed_layout_word_inside_keeps_the_instruction(): ...
def test_mixed_layout_word_in_the_window_keeps_the_instruction(): ...
```

- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** commit `feat(markers): find the spoken markers / repérer les marqueurs vocaux`.

---

### Task 6: edit file

**Files:**
- Modify: `src/podcleaner_editor/report/markdown.py`, `tests/test_markdown.py`

**Interfaces:**
- Consumes: `Filler`, `TranscriptionInfo`, `CutMap`, `merge`.
- Produces: `AnalysisResult` gains `fillers: tuple[Filler, ...] = ()`, `marker_cuts: tuple[Interval, ...] = ()`, `transcription: TranscriptionInfo | None = None`, and the property `cuts -> CutMap` = `CutMap(tuple(merge([*silence_cuts.cuts, *filler cuts, *marker_cuts])))`. The Timecodes' Final column and the durations use `cuts`. New Report layout:

```
## Report
### Duration      Final duration: 01:58:12.400 (original: 02:10:03.000), 00:11:50.600 removed.
### Tracks        (unchanged)
### Silences      214 silences shortened, 00:09:01.200 removed.
### Hesitations   153 hesitations removed (00:01:02.300), 12 flagged:
                  | Original | Final | Track | Context | Reason |   (flagged ones only)
### Markers       3 spoken markers: 2 requested cuts, 1 clip to add; 3 instructions removed (00:00:05.100).
### Overlaps      (unchanged)
### Transcription mlx-whisper large-v3-turbo · 00:58:40.000 of speech transcribed · 1 of 2 tracks from the cache.
### Claude's opinions (unchanged)
```

Without transcription (`transcription is None`), Hesitations and Markers say `Not available: the episode was not transcribed.` and the Transcription section says `None.`; with no flagged filler, no table.

- [ ] **Step 1: failing tests**: `test_final_column_counts_filler_and_marker_cuts` (silence cut 10–12 s, filler cut 20–20.5 s, event at 30 s → Final `00:00:27.500`); `test_hesitations_section_lists_flagged_only`; `test_markers_section_counts_by_type`; `test_transcription_section`; `test_without_transcription_sections_say_not_available`; `test_duration_section`. Update the M1 tests that read the old "Final duration" sentence of the Silences section.
- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** commit `feat(report): hesitations, markers and transcription in the edit file / hésitations, marqueurs et transcription dans le fichier de montage`.

---

### Task 7: pipeline, CLI and check on the test recording

**Files:**
- Modify: `src/podcleaner_editor/pipeline.py`, `tests/test_pipeline.py`, `README.md`, `README.fr.md`, `CHANGELOG.md`, `CHANGELOG.fr.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `analyze(episode, settings, *, decode=None, vad=None, transcriber: Transcriber | None = None, cache_path: Path | None = None, progress=…) -> AnalysisResult` (`transcriber` defaults to `make_transcriber(settings)`, created only on a cache miss). `run(...)` passes `cache_path = out_dir / f"{episode.name}.words.json"`. No new CLI option.
  After M1's steps (own speech, film clips), and before the silences:
  1. For each voice, in order, progress `"Transcribing <label>…"` (the first miss adds ` (the first run downloads the Whisper model, about 1.6 GB)`): passages = `speech_passages(own[i], episode.duration, passage_gap_s, passage_pad_s)`; `load_words` or else decode that track again, `transcribe_passages`, `keep_own_words(…, own[i], passage_pad_s)` (separate layout only), `save_words`, free the samples.
  2. `other_speech[label]`: separate layout, the other voice's word spans united with its own speech; mixed layout, `[]`.
  3. `find_fillers`, then `find_markers` per voice; marker events join the events.
  4. Speech cuts = the cut fillers and markers. Every voice's own-speech and loud lists given to `find_silence_cuts` become `subtract(list, speech_cuts)`; the reported silence cuts are those cuts minus the speech cuts, so no time is counted twice (the cut map is the same).
  5. `AnalysisResult(..., fillers=…, marker_cuts=…, transcription=TranscriptionInfo(transcriber name or "cache", sum of passage durations, tracks read from the cache))`.

- [ ] **Step 1: failing tests** (fake VAD as in M1, fake `Transcriber` returning fixed words per track, `cache_path` in `tmp_path`):
  - `test_marker_and_filler_in_result`: Julien says the cut phrase at 20 s and an "euh" at 40 s → one `CUT_REQUEST` event, one cut filler, Final timecodes shifted by both cuts.
  - `test_bleed_word_counted_once`: the same marker words come back on Franck's track, outside his own speech → one event, track Julien.
  - `test_euh_between_pauses_leaves_one_short_pause`: pause 0.7 s, "euh" 0.4 s, pause 0.7 s, nobody else speaking → the cut map leaves `silence_target_s` (0.4 s) of that 1.8 s stretch.
  - `test_second_run_reads_the_cache`: the second `analyze` with a transcriber that raises → same result, `transcription.cached_tracks == 2`.
  - `test_mixed_layout_fillers`: one voice file, a word that overlaps an "euh" → that filler flagged `"Other speech at the same time"`, an isolated one cut.
- [ ] **Step 2: slow tests** on `samples/pedit` (skip when absent): the expected M1 values still hold (3 overlaps, 1 film clip, silences) and the markers and "euh" counts noted in step 5 are found; the same on a mixed file built in `tmp_path` with ffmpeg (`amix` of the two voices).
- [ ] **Steps 3–4:** FAIL → implement → `uv run pytest` and `uv run pytest -m slow` → PASS.
- [ ] **Step 5: check on the test recording, with Julien**: `uv run pedit run --voice samples/pedit/pedit-full-piste-1-julien.wav --voice samples/pedit/pedit-full-piste-2-franck.wav --film samples/pedit/pedit-full-piste-3-film.wav --out out/pedit --dry-run`, twice (the second reads the cache). Note the transcription time. Julien gives the times of the markers and "euh"s he hears; compare with the `.md`, adjust the defaults that miss (prompt, `marker_min_score`, `filler_pad_s`, `filler_snap_s`), pin the counts in the slow test and record the kept values in the "Settings validated" table of `CLAUDE.md`.
- [ ] **Step 6:** README (both languages): the first run downloads the Whisper model; what the edit file now holds. CHANGELOG (both): the M2 entries.
- [ ] **Step 7:** commit `feat(pipeline): transcription, markers and hesitations in run --dry-run / transcription, marqueurs et hésitations dans run --dry-run`.
