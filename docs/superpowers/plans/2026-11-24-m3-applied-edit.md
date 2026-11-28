# M3: applied edit, implementation plan

[Français](2026-11-24-m3-applied-edit.fr.md) · **English**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pedit run` without `--dry-run` writes the edited audio.
- Each voice goes through a gate set like Julien's Strip Silence, and every track is cut at the same samples, with a crossfade at each join.
- It also writes a stereo mix that carries the markers, and a MIDI file that holds only the markers.
- The edit file has "Final" timecodes that land exactly on that audio.

**Architecture:** the M2 analysis does not change. It also computes, for each voice, the passages where the gate is open (`analysis/gate.py`), from the levels it already has. Writing forms a new package, `render/`:
- `splice.py` turns the cut map into a plan of pieces in samples, with the length of each fade (a pure function);
- `gain.py` gives the gate's gain on a block of samples;
- `writer.py` makes one streaming pass with `soundfile`, block by block, that writes every track and the mix under temporary names, then renames them;
- `markers.py` writes the MIDI file and the WAV `cue ` / `labl` chunks.

`pipeline.run` ties it all together, and the CLI drops its refusal of the mode without `--dry-run`.

**Tech Stack:** M2's. `soundfile` is already a dependency, and the MIDI file is written by hand: no new dependency.

**Spec:** [M3 design](../specs/2026-11-24-m3-applied-edit-design.md) (approved by Julien on Nov 24, 2026) · [`docs/spec.md`](../../spec.md) (the French original is authoritative) · roadmap: [`2026-11-05-roadmap.md`](2026-11-05-roadmap.md)

## Global Constraints

- The global constraints of M1 and M2 still hold:
  - platforms, `pathlib`, UTF-8;
  - English everywhere, `HH:MM:SS.mmm`;
  - commit and PR titles `type(scope): English / français`;
  - documentation in both languages.
- One branch `feat/m3-applied-edit` and one PR for the milestone, as in M2.
- Never a whole full-resolution track in memory. Reads and writes go in blocks of at most `_BLOCK_S = 5.0` seconds, across all tracks.
- Every written track has exactly the same number of samples: `n_out = n_total - cut samples`, with `n_total = round(episode.duration × rate)`.
- The cuts are those of `AnalysisResult.cuts`, and nothing else. A cut is written as `[round(start × rate), round(end × rate))`, clamped to `[0, n_total]`; an empty cut is dropped.
- Equal-power crossfade, centred on the join. The outgoing gain is `cos(π/2 · x)` and the incoming gain `sin(π/2 · x)`, with `x = (j + 0.5) / (2h)` for j = 0…2h-1. The half-length is `h = min(round(fade_ms / 1000 × rate / 2), cut // 2, piece before // 2, piece after // 2)`.
- Gate: defaults -30 dB, 0.5 s, 10 ms attack, 0.1 s release. It is decided on sound level, with the bleed test when the tracks are separate. It is never applied to the film track.
- Formats:
  - each track is written with its raw file's subtype (`soundfile.info(path).subtype`);
  - the mix is always `FLOAT`, in stereo;
  - a file over `0xFFFFFFFF` bytes becomes `RF64`, and its WAV markers are then left out, with a warning.
- Output names: `<name>.<slug(voice)>.wav`, `<name>.film.wav`, `<name>.mix.wav`, `<name>.markers.mid`.
- No half-written file stays behind after an error or a Ctrl+C.
- `--dry-run` still writes no audio.
- Fast tests generate their WAVs in `tmp_path` with `soundfile`; they use no model, no network and no `samples/`.

## Review Focus

1. **Ctrl+C or an error in the middle of writing**: no `.tmp` file stays behind. The outputs of an earlier run stay intact, since they are only replaced at the final rename. Test in task 4.
2. **A cut at the very start or the very end of the episode** (a silence before the first sentence, or after the last one): no fade that runs past the bounds, no negative index, the length stays exact. Test in task 3.
3. **Integer raw files** (16- or 24-bit PCM): each track keeps its subtype, the mix is float, and a sum above 0 dBFS stays intact in the mix. Test in task 4.
4. **Tracks of different lengths** (up to 2 s): every output has `n_out` samples, and the edit file says what was left out. Tests in tasks 4 and 6.
5. **Marker names with accents, French quotation marks or `|`**: they are written as UTF-8 in the MIDI file and in the `labl` chunks, read back unchanged, and shortened without breaking a character. Test in task 5.

---

## Files

```
src/podcleaner_editor/config.py            [gate] section (task 1)
src/podcleaner_editor/analysis/gate.py     gate_open (task 2)
src/podcleaner_editor/render/__init__.py
src/podcleaner_editor/render/splice.py     Piece, splice_plan (task 3)
src/podcleaner_editor/render/gain.py       gate_gain (task 2)
src/podcleaner_editor/render/writer.py     RenderTrack, write_edit (task 4)
src/podcleaner_editor/render/markers.py    Marker, write_midi, add_wav_markers, read_wav_markers (task 5)
src/podcleaner_editor/pipeline.py          gates in analyze, writing in run (task 6)
src/podcleaner_editor/report/markdown.py   edit mode, Files, shortened Tracks (task 6)
src/podcleaner_editor/cli.py               run without --dry-run (task 6)
tests/test_gate.py, test_splice.py, test_writer.py, test_render_markers.py
                                           + test_config, test_pipeline, test_markdown, test_cli
```

---

### Task 1: gate settings

**Files:**
- Modify: `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces new `Settings` fields, in a `[gate]` section placed right after `[silences]` in the template:

| Field | Default | TOML | Template comment |
| --- | --- | --- | --- |
| `gate_enabled: bool` | `True` | `[gate] enabled` | Silence each voice between its sentences, like Logic's Strip Silence. |
| `gate_threshold_db: float` | `-30.0` | `[gate] threshold_db` | A voice is heard above this level (dBFS). |
| `gate_min_silence_s: float` | `0.5` | `[gate] min_silence_s` | Shorter quiet moments stay open (seconds). |
| `gate_attack_s: float` | `0.010` | `[gate] attack_s` | The gate opens this long before the voice (seconds). |
| `gate_release_s: float` | `0.1` | `[gate] release_s` | The gate closes this long after the voice (seconds). |

- [ ] **Step 1: failing tests**

```python
def test_gate_settings_read_from_toml(tmp_path):
    # [gate] threshold_db = -35, enabled = false → gate_threshold_db == -35.0, gate_enabled is False
def test_template_round_trips_gate_settings(tmp_path):
    # load_settings(file written by render_template(settings_values(Settings()))) == Settings()
```

- [ ] **Step 2:** `uv run pytest tests/test_config.py` → FAIL.
- [ ] **Step 3:** add the fields and the `_KEYS` entries.
- [ ] **Step 4:** `uv run pytest` → PASS.
- [ ] **Step 5:** commit `feat(config): gate settings / réglages de la porte`.

---

### Task 2: the gate (open passages and gain)

**Files:**
- Create: `src/podcleaner_editor/analysis/gate.py`, `src/podcleaner_editor/render/__init__.py`, `src/podcleaner_editor/render/gain.py`, `tests/test_gate.py`

**Interfaces:**
- Consumes: `mask_to_intervals` (`analysis/activity.py`), `Interval`, `merge`, `Settings`.
- Produces:
  - `gate_open(levels: np.ndarray, other_levels: np.ndarray | None, hop_s: float, settings: Settings) -> list[Interval]`. A frame is open when `levels > gate_threshold_db` and, when `other_levels` is given, when `levels > other_levels - bleed_margin_db` (the `own_speech` test, over the common length of both arrays). Closings shorter than `gate_min_silence_s` are filled (`merge(…, gate_min_silence_s)`). Passages are **not** widened: `gate_gain` applies the attack and the release.
  - `gate_gain(open_passages: list[Interval], first: int, count: int, rate: int, attack_s: float, release_s: float) -> np.ndarray` (float32, length `count`): the gain of samples `[first, first + count)`.
    - It is 1 inside a passage, and 0 far from any passage.
    - Over the `attack_s` before a passage starts, it rises linearly from 0 to 1; over the `release_s` after it ends, it falls from 1 to 0.
    - Where two ramps overlap, the maximum is used.
    - It only looks at the passages that touch the block: a `bisect` search in the sorted list.

- [ ] **Step 1: failing tests**

```python
def test_gate_opens_above_threshold():
    # hop 0.01, levels -60 everywhere except -20 on frames 100–199 → [I(1.0, 2.0)]
def test_gate_fills_short_closings():
    # open 1.0–2.0 and 2.3–3.0 (0.3 s closing < 0.5 s) → [I(1.0, 3.0)]; a 0.6 s closing → two passages
def test_gate_ignores_bleed():
    # levels -25 (above the threshold) but other_levels -10 (10 dB margin) → []; other_levels=None → open
def test_gate_gain_ramps():
    # passage [1.0, 2.0], rate 1000, attack 0.01, release 0.1:
    # gain[990] ≈ 0.0, gain[995] ≈ 0.5, gain[1000:2000] == 1, gain[2050] ≈ 0.5, gain[2100:] == 0
def test_gate_gain_on_a_block_matches_the_whole():
    # gate_gain(p, 0, 3000, …)[1234:1734] == gate_gain(p, 1234, 500, …)
```

- [ ] **Step 2:** `uv run pytest tests/test_gate.py` → FAIL.
- [ ] **Step 3:** write `gate_open` and `gate_gain`.
- [ ] **Step 4:** `uv run pytest` → PASS.
- [ ] **Step 5:** commit `feat(gate): open passages and gain of the gate / passages ouverts et gain de la porte`.

---

### Task 3: the plan of pieces

**Files:**
- Create: `src/podcleaner_editor/render/splice.py`, `tests/test_splice.py`

**Interfaces:**
- Consumes: `CutMap`.
- Produces:
  - `@dataclass(frozen=True) class Piece: start: int; end: int; fade_in: int; fade_out: int`.
    - `[start, end)` is the kept piece, in samples of the original.
    - `fade_in` and `fade_out` are half-lengths h, in samples.
    - The piece is read over `[start - fade_in, end + fade_out)`.
    - Its first `2 × fade_in` samples rise and its last `2 × fade_out` samples fall.
    - In the output it starts at the sum of the earlier pieces' `end - start` lengths, minus `fade_in`.
  - `splice_plan(cuts: CutMap, n_total: int, rate: int, fade_ms: int) -> list[Piece]`. The pieces are the complement of the cuts in `[0, n_total)`, in samples; an empty piece is dropped. A join's `h` is given in the Global Constraints and shared by both pieces. The first piece has `fade_in = 0` and the last `fade_out = 0`. `sum(p.end - p.start) == n_out`.
  - `fade_curves(h: int) -> tuple[np.ndarray, np.ndarray]`: the incoming and outgoing gains (float32, length `2h`), whose squares add up to 1 at every point.

- [ ] **Step 1: failing tests**

```python
def test_no_cut_is_one_piece():                 # CutMap(()), n_total 1000 → [Piece(0, 1000, 0, 0)]
def test_one_cut_two_pieces_with_shared_fade():
    # rate 1000, fade_ms 30, cut [0.4, 0.6) → [Piece(0, 400, 0, 15), Piece(600, 1000, 15, 0)]
def test_fade_shortened_by_a_short_cut_or_piece():
    # a 10-sample cut → h = 5; an 8-sample piece between two cuts → h = 4 on both sides
def test_cut_at_start_and_end():
    # cuts [0, 0.2) and [0.9, 1.0) over 1 s → one piece Piece(200, 900, 0, 0), length 700
def test_output_length_is_exact():
    # 50 random cuts (fixed seed) → sum(end - start) == n_total - cut samples
def test_fade_curves_keep_power():
    # fade_curves(15): fade_in² + fade_out² ≈ 1 everywhere; fade_in rising, fade_out falling
```

- [ ] **Step 2:** `uv run pytest tests/test_splice.py` → FAIL.
- [ ] **Step 3:** write `Piece`, `splice_plan` and `fade_curves`.
- [ ] **Step 4:** `uv run pytest` → PASS.
- [ ] **Step 5:** commit `feat(render): plan of the kept pieces and fades / plan des morceaux gardés et des fondus`.

---

### Task 4: streaming the files to disk

**Files:**
- Create: `src/podcleaner_editor/render/writer.py`, `tests/test_writer.py`

**Interfaces:**
- Consumes: `Piece`, `splice_plan`, `fade_curves` (task 3); `gate_gain` (task 2); `EditorError`.
- Produces:
  - `@dataclass(frozen=True) class RenderTrack: source: Path; target: Path; gate: tuple[Interval, ...] | None` (`None`: no gate).
  - `write_edit(tracks: list[RenderTrack], pieces: list[Piece], n_total: int, mix_target: Path, settings: Settings) -> int`. It writes every track and the mix, and returns `n_out`.
  - `check_renderable(sources: list[Path]) -> int`. It returns the shared rate. Otherwise, `EditorError`:
    - `"The tracks do not share one sample rate ({list}): convert them to the same rate first."`;
    - `"{name} has {n} channels: only mono or stereo tracks can be edited."`.
  - `estimate_bytes(sources: list[Path], n_out: int) -> int` and the space check: when `shutil.disk_usage(folder).free < 1.05 × estimate`, `EditorError(f"Not enough disk space in {folder}: about {x:.1f} GB needed, {y:.1f} GB free.")`, raised before any file is opened.
- How it works:
  - **Reading.** Each source is opened with `soundfile.SoundFile`. The pieces are walked in order; each piece is read in blocks of at most `_BLOCK_S`, with `seek` then `read(dtype="float32", always_2d=True)`.
  - **Gate.** The `gate_gain` gain is applied according to the position in the original.
  - **Fades.** The last `2 × fade_out` samples of a piece, already faded out, are held back. The next piece's first `2 × fade_in` samples, faded in, are added to them, then the whole is written.
  - **Mix.** Each block written to the tracks is added to the same block of the mix. A mono track is copied to both channels.
  - **Safe writing.** Everything is written to `<target>.tmp` (`format="WAV"` or `"RF64"`). The `os.replace` renames happen only at the end, once everything is written. A `try` / `except BaseException` closes and deletes the `.tmp` files, then re-raises.

- [ ] **Step 1: failing tests** (ramp WAVs: sample i is `i / n`; `gate=None` unless stated)

```python
def test_tracks_cut_at_the_same_samples(tmp_path):
    # 2 tracks of 1 s at 1000 Hz, cut [0.4, 0.6), fade_ms 0 → each output = ramp[0:400] + ramp[600:1000]
def test_crossfade_at_the_join(tmp_path):
    # fade_ms 30 → length 800; out[385:415] == ramp[385:415]·cos + ramp[585:615]·sin
def test_mix_is_the_sum(tmp_path):
    # mono voice 0.5 + stereo film 0.75 → stereo mix 1.25 on both channels, subtype FLOAT
def test_integer_sources_keep_their_subtype(tmp_path):
    # PCM_24 → PCM_24 track; two tracks at 0.9 → mix 1.8, not clipped
def test_gate_applied_to_voice_only(tmp_path):
    # gate=(I(0.2, 0.3),) → outside [0.19, 0.4] the output is 0; the film track without a gate is untouched
def test_shorter_track_sets_the_length(tmp_path):
    # tracks of 1.0 s and 1.5 s, n_total = 1000 → both outputs have 1000 - cut samples
def test_error_mid_write_leaves_no_tmp_and_keeps_old_files(tmp_path, monkeypatch):
    # existing targets holding "old"; a read that raises KeyboardInterrupt on the 2nd block → no *.tmp, the targets still hold "old"
def test_different_rates_refused(tmp_path):     # 44100 and 48000 → EditorError "do not share one sample rate"
def test_more_than_two_channels_refused(tmp_path):  # 6 channels → EditorError "only mono or stereo"
def test_not_enough_space(tmp_path, monkeypatch):
    # disk_usage.free = 10 → EditorError "Not enough disk space", no file created
```

- [ ] **Step 2:** `uv run pytest tests/test_writer.py` → FAIL.
- [ ] **Step 3:** write `RenderTrack`, `check_renderable`, `estimate_bytes` and `write_edit`.
- [ ] **Step 4:** `uv run pytest` → PASS.
- [ ] **Step 5:** commit `feat(render): stream the cut tracks and the mix to disk / écrire en flux les pistes coupées et le mixage`.

---

### Task 5: the markers (MIDI and WAV)

**Files:**
- Create: `src/podcleaner_editor/render/markers.py`, `tests/test_render_markers.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Marker: time_s: float; name: str`.
  - `marker_name(kind: str, reason: str) -> str`. The name is `f"{kind}: {reason}"`, shortened to `MAX_NAME = 120` characters, `"…"` included; it is cut between characters, never in the middle of a UTF-8 byte sequence.
  - `write_midi(markers: list[Marker], path: Path) -> None`: a type 0 standard MIDI file, division 960.
    - It starts with the tempo `FF 51 03 07 A1 20` (120 bpm) at tick 0.
    - Each marker is a `FF 06 <VLQ length> <UTF-8 text>` event at tick `round(time_s × 1920)`, with VLQ deltas. Markers are sorted by time.
    - The file ends with `FF 2F 00`.
    - Safe writing: `.tmp` then `os.replace`.
  - `add_wav_markers(path: Path, markers: list[Marker], rate: int) -> bool`. It adds at the end of the file:
    - a `cue ` chunk, with one point per marker: id `k + 1`, position and `sample offset` `round(time_s × rate)`, `data`;
    - a `LIST` chunk of type `adtl`, with one `labl` per marker (UTF-8 text ending with a zero byte, plus a pad byte when the length is odd).

    Then it fixes the `RIFF` size at byte 4 and returns `True`. It leaves an `RF64` file untouched and returns `False` (task 6 gives the warning).
  - `read_wav_markers(path: Path) -> list[tuple[int, str]]` (position in samples, name), used by the tests and the slow tests.

- [ ] **Step 1: failing tests**

```python
def test_midi_bytes(tmp_path):
    # [Marker(0.5, "A"), Marker(1.0, "B")] → MThd 0/1/960; tempo; FF 06 "A" at tick 960; FF 06 "B" delta 960; FF 2F 00
def test_midi_vlq_for_long_times(tmp_path):   # Marker(7200.0, …) → delta 13,824,000 encoded as VLQ and read back unchanged
def test_wav_markers_round_trip(tmp_path):
    # stereo float WAV written by soundfile + add_wav_markers → read_wav_markers == [(22050, "Clip to add: …")]
    # and soundfile.read still reads the same audio
def test_unicode_names_round_trip(tmp_path):
    # 'Requested cut: Spoken instruction: "dis Claude, on coupe « ça » | là"' → unchanged in the MIDI file and in the WAV
def test_marker_name_is_cut_cleanly():
    # a 300-character accented reason → len == 120, ends with "…", encodes as UTF-8
```

- [ ] **Step 2:** `uv run pytest tests/test_render_markers.py` → FAIL.
- [ ] **Step 3:** write `Marker`, `marker_name`, `write_midi`, `add_wav_markers` and `read_wav_markers`.
- [ ] **Step 4:** `uv run pytest` → PASS.
- [ ] **Step 5:** commit `feat(render): markers in a MIDI file and in the mix WAV / marqueurs dans un fichier MIDI et dans le WAV du mixage`.

---

### Task 6: full chain, edit file and CLI

**Files:**
- Modify: `src/podcleaner_editor/pipeline.py`, `src/podcleaner_editor/report/markdown.py`, `src/podcleaner_editor/cli.py`, `tests/test_pipeline.py`, `tests/test_markdown.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - **In `analyze`.** When `gate_enabled` is true, `analyze` computes `gate_open` for each voice, with the other voice's levels when the tracks are separate, `None` when they are mixed. The result goes into `AnalysisResult.gates: dict[str, tuple[Interval, ...]] | None` (key: the voice's label), which is `None` when the gate is off.
  - **`AnalysisResult.outputs: tuple[Path, ...] = ()`.** These are the written files, filled in by `run`; `dry_run` is `False` in edit mode.
  - **`markers_of(result: AnalysisResult) -> list[Marker]`** (in `pipeline.py`). The list holds each event, at time `cuts.to_final(event.start)` and named `marker_name(str(event.type), event.reason)`. It also holds each flagged "euh" (`f.cut is None`), at time `cuts.to_final(f.word.start)` and named `marker_name("Hesitation", f"{f.track}: {f.reason}")`. Everything is sorted by time.
  - **`file_slug(label: str) -> str`.** It lowercases, strips accents (NFKD), replaces every run of characters other than `[a-z0-9]` with `-` and strips `-` from the ends. Examples: `"Julien + Franck"` → `"julien-franck"`, `"Élodie"` → `"elodie"`. An empty slug becomes `"voice"`. When two voices give the same slug, `-1` and `-2` are added.
  - **`run(episode, settings, out_dir, *, dry_run: bool, progress=…) -> list[Path]`.** It returns the edit file, then the audio files and the MIDI file. Without `dry_run`, it does, in order:
    1. `check_renderable` before the analysis;
    2. the analysis;
    3. `splice_plan`, the space check, then `write_edit` with the progress line `"Writing the edited tracks…"`;
    4. `add_wav_markers` on the mix; when it returns `False` (RF64), the line `"⚠ The mix is over 4 GB (RF64): its markers are only in <name>.markers.mid."`;
    5. `write_midi`;
    6. the edit file, last.
  - **Edit file.** `mode: edit` when `dry_run` is false. A new `### Files` section, placed after Duration: one `- <file name>` line per output, or `"None: dry run, no audio written."`. The Tracks section adds a `Left out at the end` column, which is `format_tc(track duration - episode.duration)` when the difference exceeds 1 ms, and `—` otherwise.
  - **CLI.** `run` without `--dry-run` no longer raises an error. The command prints `Written: <path>` for each file.

- [ ] **Step 1: failing tests** (fake VAD and fake `Transcriber` as in M2; WAVs generated at 8 kHz)
  - `test_run_writes_every_output`: separate tracks give `ep.edit.md`, `ep.<a>.wav`, `ep.<b>.wav`, `ep.film.wav`, `ep.mix.wav` and `ep.markers.mid`. Every track has the same number of samples, `round(cuts.final_duration(duration) × 8000)` within ±1 per cut. The edit file says `mode: edit` and lists these files.
  - `test_markers_match_events_and_flagged_fillers`: a `CUT_REQUEST` marker and a flagged "euh" give 2 markers, at the edit file's "Final" times, in the MIDI file as in the mix.
  - `test_gate_follows_settings`: `gate_enabled=False` gives `result.gates is None`, and the voice tracks are not zeroed.
  - `test_mixed_layout_outputs`: a single voice file (label `"A + B"`) gives `ep.a-b.wav`, `ep.film.wav` and `ep.mix.wav`.
  - `test_dry_run_writes_no_audio`: only `ep.edit.md` and `ep.words.json` are written; the edit file says `mode: dry run` and `None: dry run, no audio written.`.
  - `test_tracks_section_reports_left_out_end`: with a film track 1.5 s longer, the `Left out at the end` column says `00:00:01.500` for the film and `—` for the others.
  - `test_file_slug`: the examples above, plus the duplicate case.
  - `test_cli_run_without_dry_run` (`test_cli.py`): the exit code is 0 and the output says `Written:` at least four times.
- [ ] **Step 2:** `uv run pytest` → FAIL on these tests.
- [ ] **Step 3:** write `markers_of`, `file_slug`, the gates in `analyze`, `run(dry_run=…)`, the report sections and the CLI. Update the M1 and M2 tests that call `run` or read the Tracks section.
- [ ] **Step 4:** `uv run pytest` → PASS.
- [ ] **Step 5:** commit `feat(pipeline): write the edited tracks, the mix and the markers / écrire les pistes montées, le mixage et les marqueurs`.

---

### Task 7: check on the test recording, and documentation

**Files:**
- Modify: `tests/test_pipeline.py`, `docs/spec.md`, `docs/spec.fr.md`, `docs/superpowers/plans/2026-11-05-roadmap.md`, `docs/superpowers/plans/2026-11-05-roadmap.fr.md`, `README.md`, `README.fr.md`, `CHANGELOG.md`, `CHANGELOG.fr.md`, `CLAUDE.md`

- [ ] **Step 1: slow test** `test_pedit_edit_outputs` (skipped without `samples/pedit`):
  - `run` without `dry_run` into `tmp_path` writes the six files;
  - the four WAVs have the same number of samples, at 44,100 Hz, in `FLOAT`;
  - the duration equals the edit file's final duration, within 1 ms;
  - `read_wav_markers(mix)` has as many markers as the MIDI file, and `len(markers_of(result))` does too;
  - Julien's track is exactly 0 between two of his sentences (for example around Franck's speech near 48 s).
- [ ] **Step 2:** `uv run pytest -m slow` → PASS. Note the writing time.
- [ ] **Step 3: listening with Julien.**
  - `uv run pedit run --voice samples/pedit/pedit-full-piste-1-julien.wav --voice samples/pedit/pedit-full-piste-2-franck.wav --film samples/pedit/pedit-full-piste-3-film.wav --out out/pedit`.
  - Julien imports the tracks into Logic Pro and listens to the joins and the gate: are laughs kept, is bleed removed, are any word starts swallowed?
  - He imports `pedit.markers.mid`, then the mix's markers ("Import Marker from Audio File"), and says which of the two lands right.
  - Adjust `gate_release_s`, `gate_threshold_db` and `fade_ms` if needed, then record the chosen values and the marker format that works in the "Validated settings" table of `CLAUDE.md`.
  - Then the same on a whole episode: note the processing time and the disk space used.
- [ ] **Step 4: documentation, in both languages.**
  - Spec: the gate in the features table, and the file names in "Outputs".
  - Roadmap: the M3 row goes from "to write" to "done", with the gate.
  - README: `run` without `--dry-run`, the written files, importing into Logic.
  - Changelog: the M3 entries.
  - `CLAUDE.md`: the "Outputs" row and the gate in the decisions table; the "edited audio comes with M3" sentence of the Commands section is updated.
- [ ] **Step 5:** `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` → PASS.
- [ ] **Step 6:** commit `docs(m3): applied edit in the spec, roadmap, README and changelog / montage appliqué dans le cahier des charges, la feuille de route, le README et le journal`.
