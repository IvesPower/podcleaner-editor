# M4: studio sound, implementation plan

[Français](2026-11-28-m4-studio-sound.fr.md) · **English**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pedit run` without `--dry-run` processes the sound of each voice like Auphonic: DeepFilterNet 3, then ffmpeg filters. It brings the mix to -16 LUFS / -1 dBTP with one gain shared by every track, and reports loudness before and after in the edit file.

**Architecture:** the new `sound/` package does three things:
- `denoise.py`: a `Denoiser` protocol and the DeepFilterNet backend, streamed in slices;
- `filters.py`: the ffmpeg filter chain;
- `loudness.py`: ffmpeg `ebur128` measurements and the shared gain.

`pipeline.run` processes each voice into a temporary float WAV, which becomes the source of the M3 writer. It measures the sum and passes `gain_db` to `write_edit`. Everything else from M3 stays as it is: analysis, gate, cuts, markers.

**Tech Stack:** M3's, plus `deepfilternet` 0.5.6, `torch` 2.0.1, `torchaudio` 2.0.2, `scipy`; Python 3.11 only.

**Spec:** [M4 design](../specs/2026-11-28-m4-studio-sound-design.md) · [`docs/spec.md`](../../spec.md) (the French original is authoritative)

## Global Constraints

- The constraints of M1 to M3 still hold (platforms, `pathlib`, UTF-8, English in code and outputs, bilingual commits and docs, no whole full-resolution track in memory, fast tests without model or network, ffmpeg allowed).
- `requires-python = ">=3.11,<3.12"`; CI matrix: macOS and Windows, Python 3.11 only.
- Dependencies added: `"deepfilternet==0.5.6"`, `"torch==2.0.1"`, `"torchaudio==2.0.2"`, `"scipy"`; `uv lock`.
- Default ffmpeg filters, verbatim: `highpass=f=100,lowshelf=f=250:g=-4,equalizer=f=500:t=q:w=1:g=-1.5,equalizer=f=2500:t=q:w=1:g=-1,highshelf=f=4500:g=-7,acompressor=threshold=-26dB:ratio=3:attack=10:release=250:makeup=2`.
- DeepFilterNet runs on a mono copy at 48 kHz, in 30 s slices with 1 s overlap and a 0.5 s linear crossfade in the overlap. The result is brought back to the source rate and to the source's channel count (mono copied to every channel).
- The film track is never processed. Analyses stay on the original audio. `--dry-run` processes no sound.
- One gain for every written track and the mix: `gain = target_lufs - I(sum)`, lowered so that `TP(sum) + gain ≤ true_peak_db`.
- Temporary sound files live in the output folder, are named `.<name>.<slug>.sound.tmp.wav`, are written as 32-bit float, and are deleted at the end, after an error too.

## Review Focus

1. **First run without network.** The DeepFilterNet model cannot download: `Error: Could not load the DeepFilterNet model: …`, exit code 2, no traceback. Test in task 2.
2. **A 2 h track.** Memory stays bounded: one slice plus its overlap at a time. Slice joins are inaudible: no click and no level dip at the crossfade. Test in task 2 (the join of a constant tone).
3. **A silent or near-silent track** (a voice that never speaks): no -inf gain, no crash; the gain is 0 dB and the report says so. Test in task 3.
4. **Integer raw files** (PCM 24-bit): the processed temporary is float, and the written track keeps the raw file's subtype. Test in task 5.
5. **An error in the middle of the sound stage**: no `.sound.tmp.wav` is left behind, and earlier outputs stay intact. Test in task 5.

---

### Task 1: Python 3.11, dependencies, `[sound]` settings

**Files:** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `src/podcleaner_editor/config.py`, `tests/test_config.py`

**Interfaces:** new `Settings` fields, in a `[sound]` section right after `[gate]`:

| Field | Default | TOML | Template comment |
| --- | --- | --- | --- |
| `sound_enabled: bool` | `True` | `[sound] enabled` | Process the sound of each voice (noise, reverb, EQ, loudness). |
| `sound_denoise: bool` | `True` | `[sound] denoise` | Remove noise and reverb with DeepFilterNet before the filters. |
| `sound_filters: str` | the default chain | `[sound] filters` | ffmpeg filters applied to each voice, after the denoiser. |
| `sound_target_lufs: float` | `-16.0` | `[sound] target_lufs` | Loudness of the mix (LUFS). |
| `sound_true_peak_db: float` | `-1.0` | `[sound] true_peak_db` | Highest true peak of the mix (dBTP). |

- [ ] Failing tests: `test_sound_settings_read_from_toml` (`[sound] enabled = false`, `target_lufs = -18` → `False`, `-18.0`); the template round-trip still holds.
- [ ] Pin Python, add the dependencies, CI matrix to `python: ["3.11"]`, `uv lock`, `uv sync`; the full suite passes.
- [ ] Commit `build(sound): DeepFilterNet and the [sound] settings, Python 3.11 only / DeepFilterNet et les réglages [sound], Python 3.11 seulement`.

### Task 2: the denoiser

**Files:** create `src/podcleaner_editor/sound/__init__.py`, `sound/denoise.py`, `tests/test_denoise.py`

**Interfaces:**
- `class Denoiser(Protocol): name: str; rate: int; def __call__(self, mono: np.ndarray) -> np.ndarray` (float32 at `rate`, same length).
- `make_denoiser() -> Denoiser`: DeepFilterNet 3, `rate = 48000`, `name = "DeepFilterNet 3"`. It imports `df` and loads the model lazily, on the first call. Any exception during import or load raises `EditorError(f"Could not load the DeepFilterNet model: {exc}")`.
- `denoise_file(source: Path, target: Path, denoiser: Denoiser, *, slice_s: float = 30.0, overlap_s: float = 1.0) -> None`. It reads `source` with `soundfile` slice by slice, averages to mono, and resamples to `denoiser.rate` with `scipy.signal.resample_poly`, with a margin so the edges carry no artefacts. It applies the denoiser and crossfades linearly over the 0.5 s in the middle of each overlap. It resamples back and writes `target` as FLOAT at the source rate with the source's channel count. The output has exactly as many frames as the source.

- [ ] Failing tests:
  - `test_identity_denoiser_keeps_the_audio`: a fake that returns its input; a 70 s stereo 44.1 kHz noise file gives output equal to the mono average within 1e-3, with the same frames and channels.
  - `test_slices_join_without_a_dip`: a fake that multiplies by 0.5 and a constant 1 kHz tone; the RMS of every 10 ms frame stays within ±0.2 dB of the median.
  - `test_denoiser_sees_its_own_rate`: a fake with `rate = 48000` records the length of the arrays it receives; their total matches 48 kHz.
  - `test_model_load_failure_is_an_editor_error`: `df` import monkeypatched to raise `OSError("offline")` → `EditorError("Could not load the DeepFilterNet model: offline")`.
  - A slow `test_deepfilternet_lowers_noise`: white noise plus a tone at the start of `pedit-full-piste-1-julien.wav`, the noise floor lower after processing.
- [ ] Implement; the full suite passes; commit `feat(sound): remove noise and reverb with DeepFilterNet, slice by slice / retirer bruit et réverb avec DeepFilterNet, tranche par tranche`.

### Task 3: filters and loudness

**Files:** create `sound/filters.py`, `sound/loudness.py`, `tests/test_sound_filters.py`, `tests/test_loudness.py`

**Interfaces:**
- `apply_filters(source: Path, target: Path, filters: str) -> None`: `ffmpeg -af <filters> -c:a pcm_f32le`. An empty `filters` copies the audio. On failure, `EditorError(f"ffmpeg could not apply the sound filters: {stderr}")`.
- `@dataclass(frozen=True) class Loudness: lufs: float; true_peak_db: float`.
- `measure(paths: list[Path]) -> Loudness`: one path measures that file; several measure their sum (`amix=inputs=n:normalize=0`). It uses `ebur128=peak=true` and reads `I:` and `Peak:` from the Summary. Silence (`-inf` or below -70) gives `lufs = -70.0`.
- `shared_gain(loudness: Loudness, target_lufs: float, true_peak_db: float) -> tuple[float, bool]`: the gain in dB, and whether it was lowered for the true peak. Silence (`lufs <= -70`) gives `(0.0, False)`.

- [ ] Failing tests:
  - `measure` on a 1 kHz sine at -20 dBFS (10 s): -23 ± 0.5 LUFS (sine of amplitude 0.1), true peak -20 ± 0.5.
  - The sum of two such sines in phase is +6 dB.
  - `shared_gain(Loudness(-20, -6), -16, -1) == (4.0, False)`; `shared_gain(Loudness(-20, -3), -16, -1) == (2.0, True)`; silence → `(0.0, False)`.
  - `apply_filters` with `volume=-6dB` halves the amplitude; with `""` the audio is unchanged; a bad filter → `EditorError`.
- [ ] Implement; the full suite passes; commit `feat(sound): ffmpeg filters, loudness and the shared gain / filtres ffmpeg, volume et gain commun`.

### Task 4: gain in the writer

**Files:** `src/podcleaner_editor/render/writer.py`, `tests/test_writer.py`

**Interfaces:** `write_edit(..., gain_db: float = 0.0)`. Every track's output and the mix are multiplied by `10 ** (gain_db / 20)`, after the gate and the fades and before integer clipping. The mix stays the sum of the written tracks.

- [ ] Failing tests:
  - `test_gain_applies_to_tracks_and_mix`: +6.0206 dB doubles every track and the mix.
  - `test_mix_stays_the_sum_with_gain`.
- [ ] Implement; the full suite passes; commit `feat(render): one gain for every track and the mix / un seul gain pour toutes les pistes et le mixage`.

### Task 5: the sound stage in the pipeline, edit file, CLI

**Files:** `src/podcleaner_editor/pipeline.py`, `src/podcleaner_editor/report/markdown.py`, tests

**Interfaces:**
- `@dataclass(frozen=True) class SoundInfo: chain: str; gain_db: float; capped: bool; rows: tuple[tuple[str, Loudness, Loudness], ...]`. `chain` is one of `"DeepFilterNet 3 + filters"` or `"filters only"`. Each row is (file name, loudness of its raw source, loudness of the written file); the mix row's "before" is the raw sum.
- `AnalysisResult.sound: SoundInfo | None = None`.
- `run(..., denoiser: Denoiser | None = None)`: tests pass a fake; otherwise `make_denoiser()` runs, and only when `sound_enabled` and `sound_denoise` are true. Without `dry_run` and with `sound_enabled`, after `check_renderable` and the analysis:
  1. for each voice, progress `"Processing the sound of <label>…"` (the first one adds `" (the DeepFilterNet model is downloaded on first use)"`), then `denoise_file` (when `sound_denoise`) and `apply_filters` to the temporary;
  2. progress `"Measuring the loudness…"`, then `shared_gain(measure([*processed voices, film]), …)`;
  3. `write_edit` from the processed voices (film raw), with `gain_db`;
  4. measure each written file, then `SoundInfo`.
  The temporaries are deleted in a `finally`. The space check counts them: the processed voices' size is added to the writer's estimate. Check it in `run` before processing, with the same message as the writer.
- Edit file: a `### Sound` section after Tracks.
  - Dry run: `None: dry run, no audio written.`; disabled: `Not processed: [sound] enabled = false.`
  - Otherwise: `"<chain> · gain {gain:+.1f} dB · target {target:.1f} LUFS."`, with `" Target not reached: true peak held at {tp:.1f} dBTP."` when capped.
  - Then a table `| File | Before | After |` with cells `"{lufs:.1f} LUFS / {tp:.1f} dBTP"`.

- [ ] Failing tests (fake denoiser, small WAVs):
  - `test_run_processes_the_voices_not_the_film`;
  - `test_mix_reaches_the_target_loudness` (-16 ± 0.5);
  - `test_gain_capped_by_true_peak`;
  - `test_sound_disabled_writes_raw_levels`;
  - `test_sound_section_in_edit_file`;
  - `test_no_sound_tmp_left_after_an_error` (`apply_filters` raising);
  - `test_dry_run_processes_no_sound` (the denoiser is never called);
  - `test_pcm24_source_keeps_its_subtype`.
- [ ] Implement; full suite; commit `feat(pipeline): studio sound before the edit is written / son studio avant l'écriture du montage`.

### Task 6: test recording, listening, docs

**Files:** `tests/test_pipeline.py`, `docs/spec.md`, `docs/spec.fr.md`, roadmap (both languages), `README.md`, `README.fr.md`, `CHANGELOG.md`, `CHANGELOG.fr.md`, `CLAUDE.md`

- [ ] Slow test `test_pedit_studio_sound`: `run` on `samples/pedit`.
  - The mix is at -16 ± 0.5 LUFS with a true peak ≤ -1.0 dBTP.
  - The mean balance difference over the six bands 60–8000 Hz (relative to 800–2000 Hz) between the mix and `pedit-full-ia.mp3` (from 6.4087 s) is ≤ 2.5 dB; skip if the mp3 is missing.
  - Every written track has the same number of frames.
- [ ] `uv run pytest -m slow` → PASS. Run the real command into `out/pedit`; note the processing time.
- [ ] Docs in both languages:
  - spec: Studio sound row (DeepFilterNet + filters, WPE set aside, Python 3.11);
  - roadmap: M4 row;
  - README: install now on Python 3.11, first-run download, `[sound]`;
  - CHANGELOG: M4 entries;
  - CLAUDE.md: Son row, Python 3.11, commands.
- [ ] Commit `docs(m4): studio sound in the spec, roadmap, README and changelog / son studio dans le cahier des charges, la feuille de route, le README et le journal`.
- [ ] Listening by Julien (human step): tracks and mix against `out/m4-preview/pedit-auphonic-same-volume.wav`; tune `filters`; record the values in "Validated settings".
