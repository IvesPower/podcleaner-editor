# podcleaner-editor

[Français](README.fr.md) · **English**

A command-line tool that does the repetitive part of editing a podcast episode, from the raw recording to tracks that are ready to finish by hand in Logic Pro. It replaces Auphonic for the sound and prepares the remaining manual work with timecodes.

> **Status: early development.** The analysis works in `--dry-run` mode (milestones 1 and 2: silences, overlaps, film clips, transcription, hesitations, voice markers); no audio is written yet. See the [roadmap](docs/superpowers/plans/2026-11-05-roadmap.md).

## What it will do

- **Studio sound**: noise reduction, de-reverb, EQ, compression and de-essing on each track, then a mix normalised to -16 LUFS and -1 dBTP.
- **Silences**: shortens to about 0.4 s every silence longer than 1 s where all tracks are quiet, with a fade.
- **Hesitations**: removes isolated "uh"s that don't break the sentence, and flags the others.
- **Overlapping speech**: marks with a timecode each time someone tries to talk over the other person without taking the floor.
- **Voice markers**: finds spoken instructions to Claude, a call at the start of a sentence, "dis Claude" or "Claude" followed by a comma or a pause (so a first name such as "Claude Chabrol" does not count), then an action word, such as "Dis Claude, on va couper ce passage-là" ("Claude, we'll cut this part") or "Claude, ajoute un extrait ici" ("Claude, add a clip here"), and removes the instruction itself from the audio.
- **Film clips**: locates every clip played during the recording, from activity on the film track.
- **Cut suggestions**: proposes passages to remove, with the reason (with Claude).

`--dry-run` writes the report and timecodes without touching the audio.

## Two recording layouts

| Layout | You give | Notes |
| --- | --- | --- |
| Separate tracks | one WAV per voice + the film track WAV | everything above |
| Mixed voices | one stereo WAV holding both voices + the film track WAV | overlaps can't be detected or cut, an "uh" is only removed when nobody else speaks at the same time, one sound chain for both voices |

## Outputs

- The processed voice tracks and the film track, all cut at the same points so they stay in sync, and a stereo mix.
- One Markdown edit file per episode: timecodes (on the original and on the final audio) and a report (loudness before and after, what was removed, what was flagged).
- Markers as a MIDI file and inside the mix WAV, for Logic Pro and Cakewalk.

## Install

```bash
brew install ffmpeg            # macOS (Windows: winget install ffmpeg)
uv tool install git+https://github.com/IvesPower/podcleaner-editor
```

`podcleaner-editor` and its short alias `pedit` are the same command. In a terminal, it starts with its pixel-art title (`--no-banner` or `PODCLEANER_EDITOR_NO_BANNER=1` to hide it).

## Configure

```bash
pedit init            # a few questions, then writes your configuration file
pedit config          # shows the configuration as read, defaults included
pedit config --path   # only where the file is
```

`pedit init` asks for the folder of your edited episodes, how you record (one file per voice, or both voices on one stereo file), the first names of the two voices, and whether to use Claude; it checks that Claude Code is installed and logged in. Your current answers are offered as defaults when you run it again. Every other setting is in the file, commented. `pedit init --no-input` writes the commented file without questions.

## Run

The analysis works today, in dry-run mode: it writes the edit file, not the audio yet.

```bash
# One file per voice
pedit run --voice julien.wav --voice franck.wav --film film.wav --out "Episode 42" --dry-run

# Both voices on one stereo file
pedit run --voice voices.wav --film film.wav --out "Episode 42" --dry-run
```

This writes `Episode 42/Episode 42.edit.md`: the voice markers, the film clips and the attempts to talk over the other person, with their timecodes on the original and on the edited audio; then a report: the long silences and the "uh"s that will be removed, the "uh"s only flagged (with their timecodes and the words around them), and what was transcribed. `--name` sets the episode name (by default, the `--out` folder name). With an output folder set by `pedit init`, `--name "Episode 42"` is enough: the files go to `<output folder>/Episode 42/`.

Only the passages where someone speaks are transcribed, with Whisper (mlx-whisper on Apple silicon, faster-whisper elsewhere). The first run downloads the Whisper model, about 1.6 GB, once. The words heard are kept in `Episode 42/Episode 42.words.json`, so running again on the same files does not transcribe again.

Coming next: the edited audio itself.

## Claude, optional

All signal processing runs locally with open source tools (ffmpeg, DeepFilterNet, Silero VAD, Whisper). With [Claude Code](https://claude.com/claude-code) installed and logged in (`claude auth login`), the tool asks Claude through your Claude subscription, never through an API key, to make the judgement calls where a fixed rule fails. Claude reads the timestamped transcript, never the audio, and every opinion it gives is logged in the edit file. Without Claude Code, fixed rules are used.

## Requirements

- macOS or Windows
- Python 3.11 or 3.12, with [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/) on the `PATH` (`brew install ffmpeg` on macOS, `winget install ffmpeg` on Windows)
- Input: WAV files only

## Documentation

| Document | English | Français |
| --- | --- | --- |
| Specification | [docs/spec.md](docs/spec.md) | [docs/spec.fr.md](docs/spec.fr.md) (reference) |
| Roadmap | [roadmap](docs/superpowers/plans/2026-11-05-roadmap.md) | [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md) |
| Milestone 1 plan | [M1 plan](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.md) | [plan M1](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.fr.md) |
| Milestone 2 plan | [M2 plan](docs/superpowers/plans/2026-11-22-m2-transcription-markers.md) | [plan M2](docs/superpowers/plans/2026-11-22-m2-transcription-markers.fr.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) | [CHANGELOG.fr.md](CHANGELOG.fr.md) |

## Contributing

Pull requests are welcome. `main` is protected and every PR is approved by the maintainer. Commits and PR titles follow Conventional Commits, in English then French. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
