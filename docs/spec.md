# PodCleaner-editor: automated podcast editing, base idea

*[Version française](spec.fr.md)*

Nov 5, 2026 · @Julien

## Context and goal

The goal is a command-line tool that does the repetitive work of editing an episode, from the raw file to a file ready to finish. It replaces Auphonic for audio processing and prepares the remaining manual work with timecodes.

The tool runs on macOS and Windows and will be published as open source in a Git repository. It must stay usable without an account or API key: the features that go through Claude are a bonus, not a requirement.

## Features

| Feature | What it does | Open source tools | What Claude adds |
| --- | --- | --- | --- |
| Studio sound | Noise reduction, de-reverb, EQ, compression, de-esser on each track, then a mix normalised to -16 LUFS and -1 dBTP | ffmpeg, DeepFilterNet, nara\_wpe | Choosing the settings from each track's measurements |
| Silences | Shortens to about 0.4 s every silence longer than 1 s where all tracks are quiet, with a fade | Silero VAD per track, ffmpeg | None |
| Hesitations | Removes isolated "uh"s that don't break the sentence, flags the others | faster-whisper or mlx-whisper (word timestamps), track by track | Judging, sentence by sentence, whether a cut still sounds natural |
| Overlapping speech | Spots a person trying to talk over the other without taking the floor; sets a timecode, the fix is done by hand | Overlaps detected by VAD on each track | Discarding backchannels ("yes", "mmh") and laughs to flag only real attempts |
| Voice markers | Spots "Claude ici on veut couper" ("Claude, cut here") and "Claude ici on veut ajouter un extrait" ("Claude, add a clip here") | Whisper + fuzzy search (rapidfuzz) | Recognising variations in wording |
| Film clips | Spots each clip played, from activity on the film track | Activity detection on the dedicated track | None |
| Cut suggestions | Proposes passages to remove, with the reason | None | Reading the transcript, guided by examples from already-edited episodes |

`--dry-run` mode writes the report and the timecodes without changing the audio, to validate the settings on the first episodes.

## Architecture

The program is a Python CLI that does all processing locally. Claude is added in two places, always optional: the API for decisions that need judgement, and skills to drive the tool in natural language.

*Architecture diagram: local core, two optional Claude layers (see the list below).*

Dotted lines mark what is optional. Without an API key, the Decisions step applies fixed rules only.

- **Open source tools keep the signal processing.** Claude does not listen to the audio: it reads the timestamped transcript and the measurements. Noise reduction, normalisation and cuts stay in ffmpeg and the local models, which makes them free and reproducible.
- **Claude steps in where a rule fails.** Knowing whether an "uh" can go without breaking the sentence, recognising a badly transcribed marker, spotting an off-topic passage: these are judgements about meaning, not about the signal.
- **Skills wrap the CLI, they don't replace it.** A skill only runs in Claude Code. The CLI must therefore work on its own, for the repository's contributors and for automation. The repository's `skills/` folder then holds skills that call it: full edit, report review, tuning a difficult episode.

Points to watch, for episodes of about 2 h 10:

- **Processing time.** Each track is 2 h 10 long. Only the passages where the track is active are transcribed, which cuts the volume a lot. On an Apple Silicon Mac or a PC with an NVIDIA card it is reasonable; on a CPU only, plan to start the processing and let it run.
- **Size sent to Claude.** For cut suggestions, the sentence-level timestamped transcript of a whole episode fits in one call. To judge the "uh"s, only the sentence around each candidate is sent, without the word timestamps of the whole episode.
- **Cost per episode**, to be measured on the first test episode.
- **Reproducibility**: the opinions Claude gives are logged in the edit file.

## Outputs

- **Final tracks**: one processed track per person and the film track, cut at the same points to stay in sync, ready to drop into the editing software. A stereo mix is also produced.
- **Edit file (.md)**: a single Markdown file per episode, in two parts.
  - Timecodes: each event with its type (requested cut, clip to add, film clip, overlap, suggestion), the timecode on the original audio and on the final audio, and the reason.
  - Report: measurements before and after (LUFS, true peak) per track, the number of silences and hesitations removed, the "uh"s flagged but not cut, and the opinions Claude gave.
- **Markers**: a MIDI file that contains only the markers, and the same markers written into the mix WAV. Logic Pro and Cakewalk can read one or the other; the right format is to be confirmed by testing in each application.

All analysis runs on the original audio. The program keeps the cut map to remap every timecode onto the final file.

## Out of scope, decisions and open questions

The first version does not do the creative editing (choice of clips, order of sequences, sound design) nor the publication of the episode.

| Topic | Decision |
| --- | --- |
| Recording | Always two people, one track each, plus the film track |
| Raw format | WAV only, at the best recording quality |
| Episode length | About 2 h 10 |
| Film clips | Played live during the recording, on a separate track |
| Editing software | Logic Pro |
| Sound reference | Several raw episodes with their Auphonic-processed version |
| Style reference | Several dozen hours of edited episodes, with their raw recordings without the film clips |
| Overlaps | Timecode only, no automatic volume reduction |
| Output file | A single .md per episode: timecodes and report |
| Claude API | The transcript may be sent to it |

The raw / Auphonic pairs serve as a test bench: each version of the processing is measured against them (loudness, spectrum, background noise) before it is released.

The raw recordings don't contain the film clips: transcript alignment treats them as additions and does not count them as cuts.

No open questions at this stage: the brief is complete enough to start.

## Tools to develop the project

The project is developed in Claude Code with a few general-purpose plugins, three MCP servers and skills written for the project. A few well-chosen tools are better: each loaded plugin takes up part of the context.

| Tool | Type | What it is for here | Where to find it |
| --- | --- | --- | --- |
| Superpowers | Skills | Plans, tests written before the code, methodical debugging, module by module | obra/superpowers |
| feature-dev | Plugin | Frames each feature in phases, from exploration to review | Official Anthropic marketplace |
| python-development | Plugin | Python specialist agent (packaging, typing, tests) | wshobson/agents |
| skill-creator | Skill | Writing the project's own skills | anthropics/skills |
| Ruff and pytest hooks | Hooks | Lint and tests run after each change to a Python file | the repository's `.claude/settings.json` |
| GitHub | MCP | Issues, pull requests and CI of the open source repository | github/github-mcp-server |
| Context7 | MCP | Up-to-date documentation for faster-whisper, DeepFilterNet, Silero VAD, ffmpeg | upstash/context7 |
| Hugging Face | MCP | Finding and comparing audio and transcription models | Official Hugging Face MCP server |

Skills to write for the project, versioned in `.claude/skills/`:

- **Auphonic comparison**: processes a reference episode and compares the output with the Auphonic version (LUFS, true peak, spectrum, background noise).
- **Quick test**: runs the whole chain on a 10-minute excerpt of the two tracks and the film track, to check a change without processing 2 h 10.
- **Windows compatibility**: checks paths, the presence of ffmpeg and file encoding before each release.

A `CLAUDE.md` file at the root restates the decisions of this document. Claude Code reads it at the start of each session.

Sources: [Dupple, best Claude Code skills 2026](https://dupple.com/learn/best-claude-code-skills-2026) · [Redwerk, best Claude Code plugins 2026](https://redwerk.com/blog/best-claude-code-plugins/)
