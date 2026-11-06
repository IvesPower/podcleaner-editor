# PodCleaner-editor

*[Version française](README.fr.md)*

A command-line tool that does the repetitive part of editing a podcast episode, from the raw recording to a file that is ready to finish by hand. It replaces Auphonic for audio processing and prepares the remaining manual work with timecodes.

> **Status: early development.** Nothing is usable yet. The first milestone (analysis and `--dry-run` report) is in progress; see the [roadmap](docs/superpowers/plans/2026-11-05-roadmap.md).

## What it will do

- **Studio sound**: noise reduction, de-reverb, EQ, compression and de-essing on each track, then a mix normalised to -16 LUFS and -1 dBTP.
- **Silences**: shortens to about 0.4 s every silence longer than 1 s where all tracks are quiet, with a fade.
- **Hesitations**: removes isolated "uh"s that don't break the sentence, and flags the others.
- **Overlapping speech**: marks with a timecode each time someone tries to talk over the other person without taking the floor.
- **Voice markers**: finds spoken cues such as "Claude, cut here" or "Claude, add a clip here".
- **Film clips**: locates every clip played during the recording, from activity on the film track.
- **Cut suggestions**: proposes passages to remove, with the reason (optional, uses the Claude API).

`--dry-run` writes the report and timecodes without touching the audio.

## Outputs

- One processed track per speaker plus the film track, all cut at the same points so they stay in sync, and a stereo mix.
- One Markdown edit file per episode: timecodes (on the original and on the final audio) and a report (loudness before and after, what was removed, what was flagged).
- Markers as a MIDI file and inside the mix WAV, for Logic Pro and Cakewalk.

## Principles

- **Local first.** All signal processing runs locally with open source tools (ffmpeg, DeepFilterNet, Silero VAD, Whisper). No account or API key is required.
- **Claude is optional.** With an API key, Claude reads the timestamped transcript (never the audio) to make the judgement calls where a fixed rule fails. Every opinion it gives is logged in the edit file.
- **macOS and Windows.**

## Requirements

- Python 3.11 or 3.12, managed with [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/) on the `PATH` (`brew install ffmpeg` on macOS, `winget install ffmpeg` on Windows)
- Input: WAV files only; two voice tracks (one per person) and one film track

Installation and usage instructions will come with the first release.

## Documentation

| Document | English | Français |
| --- | --- | --- |
| Project brief | [docs/spec.md](docs/spec.md) | [docs/spec.fr.md](docs/spec.fr.md) |
| Roadmap | [roadmap](docs/superpowers/plans/2026-11-05-roadmap.md) | [feuille de route](docs/superpowers/plans/2026-11-05-roadmap.fr.md) |
| Milestone 1 plan | [M1 plan](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.md) | [plan M1](docs/superpowers/plans/2026-11-05-m1-foundations-analysis.fr.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) | [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md) |

## License

[MIT](LICENSE)
