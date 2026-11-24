# M3: applied edit, design

[Français](2026-11-24-m3-applied-edit-design.fr.md) · **English**

Nov 24, 2026 · discussed with Julien

## Intent

So far, `pedit run` only writes the edit file (`--dry-run`). With M3 it writes the edited audio. Julien imports the tracks into Logic Pro, listens to the edit from start to finish, then finishes it by hand: he adds cuts and inserts the film clips where the markers say.

Today he does this repetitive work himself in Logic:

1. **Strip Silence** on each voice track (-30 dB, 0.5 s, 10 ms attack): each person is left with only their own voice, with digital silence between their sentences. No more bleed from the other mic, no more background hiss.
2. **Edit / move / shuffle left** on all tracks together: the gaps where everyone is quiet close up everywhere at once.
3. He **joins the tracks** into one.

M3 automates these three steps, adds the cuts the analysis already finds (isolated "euh"s, spoken instructions) and places markers for the rest of the work.

**It succeeds if** Julien drops the tracks into Logic and spends his time listening and finishing, not repairing cuts: no clicks at the joins, tracks that stay in sync to the last second, and markers that land in the right place.

## Goals

- One track per voice (or the mixed voices track) and the film track, **cut at the same places, to the sample**.
- On each voice track, a **gate** set like Julien's Strip Silence.
- A **crossfade** at every join.
- A **stereo mix** (sum of the tracks).
- The **markers** in a MIDI file and in the mix WAV.
- An edit file whose "Final" timecodes match the written audio exactly.

## Non-goals

- **Studio sound** (denoising, EQ, compression, normalisation to -16 LUFS / -1 dBTP): that is M4. The M3 mix is a raw sum, with no normalisation.
- **Final Cut Pro XML file** for Logic, with regions one could stretch to undo a cut: set aside for now, too uncertain without a test in Logic (fades and markers poorly documented). To reconsider if bad cuts turn out to be frequent.
- **Claude's opinions**: that is M5.

## Anti-goals (what would make the milestone a failure even if everything "works")

- Tracks that drift apart, even by one sample.
- "Final" timecodes that do not land on the written audio.
- Clicks or audible cuts at the joins.
- Loading a whole 2 h 10 track into memory.
- A gate that swallows laughs and short reactions.
- A half-written file left in the output folder after an error or an interruption.

## Constraints

- Julien's raw files are 44.1 kHz, 32-bit float, stereo, including the single-voice tracks. A 2 h 10 episode weighs about 2.3 GB per track: everything is streamed, block by block.
- A few hundred cuts per episode (about 200 silences and 150 "euh"s).
- macOS and Windows; paths through `pathlib`; everything works without Claude.
- Every analysis stays on the original audio, as in M1 and M2. M3 changes no detection.
- `soundfile` (libsndfile) is already a dependency.

## Approaches considered

| Approach | What it gives | Set aside because |
| --- | --- | --- |
| **1. A streaming pass in Python with `soundfile`** (chosen) | Sample-exact cuts, gate and fades computed in numpy, every track and the mix written in the same pass, bounded memory, easy to test on small arrays | — |
| 2. One ffmpeg command per track (`atrim` + `afade` + `concat` per piece) | No audio code to write | With hundreds of pieces, ffmpeg buffers everything waiting its turn and overflows on 2 h 10; an error in a 350-branch graph is unreadable |
| 3. ffmpeg concat list (`concat` with `inpoint` / `outpoint`) | Fast and simple | No fades: a possible click at every join |
| 4. A Final Cut Pro XML file on top of the cut files | Cuts that can be undone in Logic by stretching a region | Too uncertain: Logic's documentation says nothing about fades or markers on import (see Non-goals) |

Julien chose approach 1.

## What was decided

### The outputs

In the episode folder, next to `<name>.edit.md` and `<name>.words.json`:

| File | Content |
| --- | --- |
| `<name>.<voice>.wav` | One track per voice, gated and cut (`separate`), or the mixed voices track (`mixed`) |
| `<name>.film.wav` | The film track, cut, no gate |
| `<name>.mix.wav` | The stereo mix, with the markers written in it |
| `<name>.markers.mid` | A MIDI file that holds only the markers |

`<voice>` is the first name from the configuration, reduced to a file name that is safe on macOS and Windows (for example `julien`, `julien-franck` for mixed voices), numbered (`film-1`, `mix-1`) when it would take the name of the film track or of the mix. *Claude's call.*

Files are written in **the same format as the raw files**: same rate, same encoding (32-bit float for Julien), same channels. The mix is stereo, always in 32-bit float. *Claude's call.*

`--dry-run` does not change: report and timecodes, no audio.

### The gate (like Julien's Strip Silence)

On each voice track, the audio is brought down to zero (digital silence) where the person is not speaking.

- Defaults, Julien's values in Logic, in a new `[gate]` section: `threshold_db = -30`, `min_silence_s = 0.5`, `attack_s = 0.010`, and `release_s = 0.1`. *The `release_s` value is Claude's call: Julien gave no "post release"; to check by ear.* An `enabled` key (`true` by default) can turn the gate off.
- **Decided on sound level, not on speech detection**, to keep laughs, audible breaths and short reactions, as Strip Silence does.
- A frame is "open" when its level is above `threshold_db`. With separate tracks, it must also pass the bleed test the analysis already uses: this mic is not more than `bleed_margin_db` below the other one. Otherwise Franck's voice in Julien's mic would reopen Julien's gate. With mixed voices, only the threshold counts.
- Closings shorter than `min_silence_s` are filled in: the gate stays open between two syllables or two words.
- Each open passage starts `attack_s` earlier, with the gain rising from 0 to 1 over that time. It ends `release_s` later, with the gain falling from 1 to 0. No click on opening or closing.
- Levels come from the existing analysis (`level_hop_s` = 10 ms frames on the 16 kHz copy). The open passages, in seconds, are then applied to the full-resolution audio.
- The gate applies to the original audio, before the cuts. It changes neither detections nor timecodes.
- **The open passages are computed by `analyze()`**, which already holds the levels, and kept in `AnalysisResult`. So writing does not have to decode each track a second time for its levels. `--dry-run` computes them too, and writes nothing. The edit file does not list them. *Claude's call.*
- The film track has no gate.

### The cuts and the fades

- The cuts are the ones the analysis already computes (`AnalysisResult.cuts`: shortened silences, cut "euh"s, removed instructions). One list, applied the same way to every track.
- Times are converted to samples once, as `round(t × rate)`. All the tracks have the same rate (otherwise an error, see below), so they are cut at the same samples.
- At each join, an **equal-power crossfade** (sine / cosine) of `fade_ms` (30 ms by default), **centred on the join point**. The end of the piece before runs 15 ms into the removed part while fading out, the start of the piece after begins 15 ms early while fading in, and the two overlap. **The final duration stays exactly the cut map's.**
- If a cut or a kept piece is shorter than the fade, the fade is shortened to that length.
- **Tracks of different lengths** (up to `max_duration_mismatch_s`, 2 s by default, accepted at load time): every track stops at the shortest one (`Episode.duration`, converted to samples). That is already the duration the analysis and the cut map work on. The Tracks section of the edit file says, for each shortened track, how many seconds of its end were left out. *Claude's call.*
- Each track gets the gate, then the crossfades. The mix is the sum of the tracks once cut.

### The mix

- The sum of the cut tracks: voices (or mixed voices) and film, each at gain 1. A mono track is placed in the centre (copied to both channels).
- No normalisation and no limiter: in 32-bit float, a sum above 0 dBFS does not clip in the file. M4 will normalise. If the raw files are integers (16 or 24 bits), the mix is written in 32-bit float for the same reason. *Claude's call.*

### The markers

- **What becomes a marker**: every event of the edit file (requested cuts, clips to add, film clips, overlaps), plus the "euh"s flagged but not cut. Those are exactly the places where Julien may want to cut. *Proposed by Claude, not contradicted by Julien.*
- **Position**: the "Final" timecode of the event's start, the same as in the edit file.
- **Name**: the type then the reason, for example `Clip to add: Spoken instruction: "dis Claude, ajoute l'extrait…"`, cut to a reasonable length. *Claude's call.*
- **MIDI file**: a type 0 standard MIDI file holding only a fixed tempo (120 bpm) and one "marker" meta event (FF 06) per marker, at the right position in ticks. Written by hand, with no new dependency. *Claude's call.*
- **Mix WAV**: a `cue ` chunk and a `LIST`/`adtl` chunk with one `labl` per marker, added after the mix's audio data, while it is still the `.tmp` file, before it replaces the old mix; left out, as for RF64, if they would take the file past 4 GiB. Logic can read these markers ("Import Marker from Audio File").
- Which format Logic reads best, and whether the MIDI file lands at the start of the project: to check in Logic. The roadmap plans it for M6. Julien can tell from the first M3 test.

### The edit file

- `mode: edit` instead of `dry run`.
- A new `### Files` section lists the written files.
- The Duration section gives the real duration of the written tracks, which must equal the computed final duration.

### The CLI and writing the files

- `pedit run` without `--dry-run` writes everything. The "Writing the edited audio comes in a later version" message goes away.
- Progress prints one line per step, for example `Writing the edited tracks…`, then the path of each written file.
- **Safe writing**: each file is written under a temporary name in the same folder, then renamed at the end. An error or a Ctrl+C leaves no half-written file, and the temporary files are deleted. Files from an earlier run are replaced without asking, since the same episode is often run again. *Claude's call.*
- **Disk space**: before writing, the program estimates the size of the outputs and stops at once with an `EditorError` if there is not enough room. It does not stop after ten minutes of writing. *Claude's call.*
- **Different rates** between tracks: `EditorError` in edit mode, since they can neither be cut at the same samples nor mixed. `--dry-run` still accepts them. *Claude's call.*
- **More than 2 channels** on a track: `EditorError` in edit mode, since the mix does not know where to place them. *Claude's call.*
- **More than 4 GB** for one file (for example 2 h 10 at 96 kHz float stereo): the classic WAV format cannot hold it. The file is written as RF64, which Logic reads. The markers then stay only in the MIDI file, and a warning says so. *Claude's call; a case Julien's current raw files do not hit.*

### Tests

- **Fast tests** on WAVs generated in `tmp_path`, for example a ramp signal where each sample has a known value. They check:
  - that each track is cut at the same samples and has the exact final duration;
  - the shape of the crossfades and how they shorten;
  - the gate: threshold, filling of short closings, attack and release, bleed test;
  - the mix sum and the mono → stereo step;
  - the bytes of the MIDI file (read back by a small test reader);
  - the `cue ` / `labl` chunks read back from the WAV, which `soundfile` must still be able to read;
  - that no temporary files are left after an error;
  - lack of disk space and different rates.
- **Slow tests** on `samples/pedit` (skipped without the files): `run` without `--dry-run` writes the four expected files. Durations equal the final duration, the tracks are in sync (same sample count), and the mix carries as many markers as the MIDI file.
- **Listening with Julien** on the test recording, then on a whole episode: check the joins, the gate (laughs kept, bleed removed) and the import in Logic of the MIDI and of the WAV markers. Adjust the defaults and record them in the "Validated settings" table of `CLAUDE.md`.

### Documents to update (in both languages)

- The spec: the gate in the features table and in "Outputs".
- The roadmap: the M3 row.
- The README and the changelog.
- `CLAUDE.md`: the gate and the outputs in the decisions table.

## Left to the builder

- The split into modules. For example: `render/gate.py` (the open passages), `render/splice.py` (the plan of pieces and fades in samples), `render/writer.py` (the streaming pass), `render/markers.py` (MIDI and WAV chunks). Another split is fine too, as long as computing the plan stays pure and testable without files.
- The size of the blocks read and written (on the order of a few seconds of audio).
- Reading every track together, or one track at a time plus an accumulated mix. The builder chooses, as long as memory stays bounded and writing stays correct.
- The maximum length of a marker name.
