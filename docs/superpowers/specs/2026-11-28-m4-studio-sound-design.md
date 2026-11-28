# M4: studio sound, design

[Français](2026-11-28-m4-studio-sound-design.fr.md) · **English**

Nov 28, 2026 · after Julien listened to M3

## Intent

Julien listened to the M3 edit of the test recording: "a good first draft", but the sound still needs real work, starting with the reverb. The target is the Auphonic version of the same recording (`samples/pedit/pedit-full-ia.mp3`, without the jingles at the start and the end). Julien does not know the settings: Auphonic ran in automatic mode.

**It succeeds if**, by ear, the voices of the edited tracks and of the mix sound like the Auphonic version: dry, no "box" sound, at the same loudness, no hiss in the pauses.

## What Auphonic does to the test recording (measured Nov 28, 2026)

| Measure | Raw | Auphonic |
| --- | --- | --- |
| Likeness to the raw file (correlation, 10 s slices) | — | 0.94 to 0.97: a light touch |
| Energy changed versus the raw file | — | -9 dB, noise and reverb reduction, EQ and loudness included |
| Integrated loudness / loudness range (LRA) | -14.4 LUFS / 10 LU | -15.8 LUFS / 4.6 LU |
| Balance (relative to 800–2000 Hz) | — | ~-3 dB below 300 Hz, -2 dB around 300–800 Hz, much softer highs above 4 kHz |

Trials of Nov 28, 2026, on Julien's track:

- **WPE** (`nara_wpe`, planned in the roadmap) changes almost nothing: -35 to -47 dB. The recording has little long tail; what Julien hears is rather the room's colour (early reflections, "box").
- **DeepFilterNet 3** changes the energy by -18 dB: it removes noise and short reverb, on the same order as Auphonic.
- DeepFilterNet followed by EQ, a compressor and loudness ("v5", in `out/m4-preview/`) gets within 1.6 dB on average of Auphonic's balance, -16 LUFS, LRA 4.9.

## Goals

- A **chain per voice track** (or one for mixed voices): DeepFilterNet (noise and reverb), then ffmpeg filters (high-pass, EQ, compressor, softer highs).
- A **mix at -16 LUFS and -1 dBTP**: the film first gets its own gain to the voices' loudness, then one gain is applied to every track; the mix stays the sum of the tracks, as in M3.
- **Before and after measurements** (LUFS and true peak) per track in the edit file, as the spec asks.
- A chain **tunable without touching the code**: the ffmpeg filters are a configuration key, to tune by ear.

## Non-goals

- Copying Auphonic exactly, or its jingles.
- Claude's opinion on the settings (M5).
- An automatic test bench over several raw / Auphonic pairs: only one pair exists so far; the measuring script stays in the slow tests.
- WPE: set aside, it changes almost nothing here.

## Anti-goals

- Metallic or "underwater" voices, or swallowed word starts: DeepFilterNet too strong would be worse than the reverb.
- A mix that is no longer the sum of the tracks: Julien finishes the edit in Logic on the tracks.
- A 2 h 10 track in memory, or processing that takes longer than the analysis.
- A run without network that crashes on the first model download without a clear message.

## Constraints

- **Python 3.11 only**: `deepfilterlib` has no ready-made package for 3.12 on Apple silicon Macs, and DeepFilterNet 0.5.6 needs `torch` 2.0.1 / `torchaudio` 2.0.2 (later torchaudio versions break its import). The project moves to `requires-python = ">=3.11,<3.12"`, and CI no longer tests 3.12. Everything resolves with the current dependencies (numpy 1.26). *Claude's call.*
- The DeepFilterNet 3 model is downloaded on the first run; the progress line says so, as for Whisper.
- Everything streamed: DeepFilterNet in 30 s slices with 1 s overlap and a 0.5 s crossfade; ffmpeg reads and writes as a stream.
- `--dry-run` still writes no audio: no sound processing.

## Approaches

| Approach | What it gives | Decision |
| --- | --- | --- |
| **DeepFilterNet + ffmpeg filters + shared gain** | Closest to Auphonic in the measurements, fast (~3 min per 2 h 10 track), tunable by ear | **Chosen** (Julien: "let's just do M4") |
| WPE + ffmpeg filters | No heavy dependency | Set aside: changes almost nothing on these recordings |
| ffmpeg only (`afftdn`, EQ, compressor) | No dependency | Kept as the fallback when `denoise = false`; does not remove reverb |
| `loudnorm` on the mix alone | Simple | Set aside: the mix would no longer be the sum of the tracks and would lose its markers |

## What is decided

### The chain of one voice track

1. **DeepFilterNet 3** (noise and reverb), on a mono 48 kHz copy of the track, brought back to its own rate and channels. Can be turned off (`[sound] denoise = false`).
2. **ffmpeg filters** (`[sound] filters`), by default those of "v5":
   `highpass=f=100,lowshelf=f=250:g=-4,equalizer=f=500:t=q:w=1:g=-1.5,equalizer=f=2500:t=q:w=1:g=-1,highshelf=f=4500:g=-7,acompressor=threshold=-26dB:ratio=3:attack=10:release=250:makeup=2`
3. The result is written to a temporary file in the output folder (`.<name>.<voice>.sound.tmp.wav`, 32-bit float), which replaces the raw file as the source of the M3 writer, then is deleted.

The film track is not processed. The M3 gate and cuts then apply unchanged; the analyses stay on the original audio.

### Loudness

- Measure (ffmpeg `ebur128`, true peak) before the cuts: silences barely count in an integrated loudness measured with its gates.
- Film gain = `I(processed voices) - I(raw film)`, kept within -20 to +10 dB (0 when either is silent): the film clips play at the voices' level, as Auphonic does. On `samples/pedit` the raw film clip is 5.4 LU louder than the speech and peaks at -1.0 dBTP; without this gain the true peak held the shared gain at 0 dB and the mix at -18.7 LUFS.
- Shared gain = `target_lufs - I`, `I` measured on the sum of the processed voices and the film at its film gain, lowered if needed so the true peak of that sum stays under `true_peak_db`; the edit file then says the target was not reached.
- The M3 writer applies the film gain to the film (`RenderTrack(..., gain_db=…)`) and the shared gain to each track and so to the mix (`write_edit(..., gain_db=…)`).
- `[sound]` settings: `enabled = true`, `denoise = true`, `filters` (above), `target_lufs = -16.0`, `true_peak_db = -1.0`.

### The edit file

A new `### Sound` section:
- the chain (`DeepFilterNet 3 + filters`, `filters only`, or `Not processed` when `enabled = false`) the film gain and the shared gain applied;
- one table row per written track and for the mix: LUFS and true peak before (the raw file) and after (the written file).

### Disk and time

- The space check also counts the sound's temporary files.
- Progress: `Processing the sound of <voice>… (the DeepFilterNet model is downloaded on first use)`, then `Measuring the loudness…`.

## Left to the builder

- The split into modules (for example `sound/denoise.py`, `sound/filters.py`, `sound/loudness.py`), as long as the denoiser sits behind a protocol a test can replace with a fake.
- The details of the crossfade between DeepFilterNet slices.
- How to read the true peak from ffmpeg's output.

## Checks

- Fast tests with a fake denoiser (ffmpeg allowed).
- Slow test on `samples/pedit`: the full chain, mix at -16 ± 0.5 LUFS and true peak ≤ -1 dBTP; mean balance difference with Auphonic ≤ 2.5 dB.
- **Listening by Julien**, tracks and mix against `out/m4-preview/pedit-auphonic-same-volume.wav`, then tuning of `filters` and the chosen values recorded in "Validated settings" in `CLAUDE.md`.
