# PodCleaner-editor: automated podcast editing, base idea

[Français](spec.fr.md) · **English** — translated from the French original, which remains the reference.

Nov 5, 2026 · @Julien — revised Nov 21, 2026 (stereo track with both voices, Claude through the built-in account, CLI interface), revised Nov 23, 2026 (voice markers: call to Claude and action verb), revised Nov 24, 2026 (gate, edit outputs), revised Nov 28, 2026 (instructions kept in the audio, plain markers), revised Nov 28, 2026 (studio sound: DeepFilterNet 3 and ffmpeg filters, WPE set aside)

## Context and goal

The goal is a command-line tool that does the repetitive work of editing an episode, from the raw file to a file ready to finish. It replaces Auphonic for audio processing and prepares the remaining manual work with timecodes.

The tool runs on macOS and Windows and is published as open source on GitHub. It must stay usable without Claude: the features that go through Claude are a bonus, not a requirement. Claude is reached through the built-in account (the Claude subscription, via the Claude Code CLI), never through an API key.

## Features

| Feature | What it does | Open source tools | What Claude adds |
| --- | --- | --- | --- |
| Studio sound | DeepFilterNet 3 (noise and reverb) then ffmpeg filters (high-pass, EQ, compressor) on each voice track, then one shared gain on every track and the mix, to -16 LUFS and -1 dBTP. WPE (`nara_wpe`) was tried and set aside: it changes almost nothing on these recordings | ffmpeg, DeepFilterNet | Choosing the settings from each track's measurements |
| Gate | On each voice track, brings the passages where the person is not speaking down to digital silence, like Logic Pro's Strip Silence (-30 dB, 0.5 s, 10 ms attack, 0.1 s release). Decided on sound level, with the bleed test, not on speech detection: laughs and breaths stay | Levels from the analysis, numpy | None |
| Silences | Shortens to about 0.4 s every silence longer than 1 s where all tracks are quiet, with a fade | Silero VAD per track, ffmpeg | None |
| Hesitations | Removes isolated "uh"s that don't break the sentence, flags the others | faster-whisper or mlx-whisper (word timestamps), track by track | Judging, sentence by sentence, whether a cut still sounds natural |
| Overlapping speech | Spots a person trying to talk over the other without taking the floor; sets a timecode, the fix is done by hand. Only with one track per voice | Overlaps detected by VAD on each track | Discarding backchannels ("yes", "mmh") and laughs to flag only real attempts |
| Voice markers | Spots a call to Claude at the start of a sentence ("dis Claude, …" or "Claude, …") followed by an instruction that holds an action verb: couper, supprimer… ("cut", "delete") for a requested cut; ajouter, extrait… ("add", "clip") for a clip to add. The instruction stays in the audio, with a marker: it is cut by hand during the edit | Whisper + rules on words (rapidfuzz for the trigger) | Recognising variations in wording |
| Film clips | Spots each clip played, from activity on the film track | Activity detection on the dedicated track | None |
| Cut suggestions | Proposes passages to remove, with the reason | None | Reading the transcript, guided by examples from already-edited episodes |

`--dry-run` mode writes the report and the timecodes without changing the audio, to validate the settings on the first episodes.

## Accepted recording layouts

An episode comes in one of two layouts, always with the film track on its own:

| Layout | Files | What changes |
| --- | --- | --- |
| Separate tracks (`separate`) | One WAV per voice (two) + the film track WAV | All the processing described here |
| Mixed voices (`mixed`) | One stereo WAV holding both voices + the film track WAV | See below |

With mixed voices, the two people cannot be told apart:

- **Overlaps**: neither detected nor cut. The report says they are not available for this episode.
- **Hesitations**: an "uh" is removed only if nobody else speaks at the same time (no other transcribed word inside the cut window); otherwise it is only flagged.
- **Studio sound**: a single processing chain, tuned for both voices together.
- **Silences, voice markers, film clips, suggestions**: unchanged.
- **Outputs**: the processed voices track and the film track, cut at the same points, plus the stereo mix.

The layout comes from the number of voice files given to the command (one or two), or from the answer given to the `init` wizard.

## Architecture

The program is a Python CLI that does all processing locally. Claude is added in two places, always optional: the Claude Code CLI in non-interactive mode (`claude -p`, with the person's subscription) for decisions that need judgement, and skills to drive the tool in natural language.

*Architecture diagram: local core, two optional Claude layers (see the list below).*

Dotted lines mark what is optional. Without a logged-in Claude Code, the Decisions step applies fixed rules only.

- **Open source tools keep the signal processing.** Claude does not listen to the audio: it reads the timestamped transcript and the measurements. Noise reduction, normalisation and cuts stay in ffmpeg and the local models, which makes them free and reproducible.
- **Claude steps in where a rule fails.** Knowing whether an "uh" can go without breaking the sentence, recognising a badly transcribed marker, spotting an off-topic passage: these are judgements about meaning, not about the signal.
- **Claude goes through the built-in account.** The program runs the installed, logged-in Claude Code CLI (`claude auth login`), with no tools, no saved session, no settings or MCP, from a temporary folder, and with no `ANTHROPIC_API_KEY` in its environment. If the CLI is missing, not logged in or returns an error, the program carries on with the fixed rules and says so.
- **Skills wrap the CLI, they don't replace it.** A skill only runs in Claude Code. The CLI must therefore work on its own, for the repository's contributors and for automation. The repository's `skills/` folder then holds skills that call it: full edit, report review, tuning a difficult episode.

Points to watch, for episodes of about 2 h 10:

- **Processing time.** Each track is 2 h 10 long. Only the passages where the track is active are transcribed, which cuts the volume a lot. On an Apple Silicon Mac or a PC with an NVIDIA card it is reasonable; on a CPU only, plan to start the processing and let it run.
- **Size sent to Claude.** For cut suggestions, the sentence-level timestamped transcript of a whole episode fits in one call. To judge the "uh"s, only the sentence around each candidate is sent, without the word timestamps of the whole episode.
- **Subscription use per episode** (number of calls, time), to be measured on the first test episode.
- **Reproducibility**: the opinions Claude gives are logged in the edit file.

## Command-line interface

- **Name**: `podcleaner-editor`, with the short alias `pedit`. Install: `uv tool install git+https://github.com/IvesPower/podcleaner-editor`.
- **Commands**: `init`, `run`, `config [--path]`, `version` (and `--version`). The command alone prints the help.
- **Banner**: the name in pixel art in the podcast's colours (cream #fbf2f1 letters on a rust #94380c badge, as in podcleaner-clips) at the start of `init`, `run` and the command alone; never outside a terminal; `--no-banner` or `PODCLEANER_EDITOR_NO_BANNER=1`; a one-line title when the terminal is too narrow or cannot draw the blocks.
- **`init` wizard**: asks the questions in the console (output folder, recording layout, first names of the two voices, Claude yes or no, checking that Claude Code is logged in) and writes the commented configuration file with the answers; offers the current values as defaults; replaces an existing file after confirmation. Outside a terminal or with `--no-input`: the commented template, without questions.
- **Configuration**: one TOML file per person, in the user's configuration folder, overridable with `--config` or `PODCLEANER_EDITOR_CONFIG`; no hard-coded path.
- **Progress**: one line per step during `run`, then the paths of the files written.

## Outputs

- **Final tracks**: one processed track per person (or the voices track, when they come mixed) and the film track, cut at the same points, to the sample, with a crossfade at every join, to stay in sync and ready to drop into the editing software. Each voice track goes through the gate first. A stereo mix (sum of the tracks) is also produced; the voices go through the studio sound first, and every track and the mix share one gain. Files: `<name>.<voice>.wav` (one per voice), `<name>.film.wav`, `<name>.mix.wav`, `<name>.markers.mid`, next to `<name>.edit.md`. Without `--dry-run` only.
- **Edit file (.md)**: a single Markdown file per episode, in English, in two parts.
  - Timecodes: each event with its type (requested cut, clip to add, film clip, overlap, suggestion), the timecode on the original audio and on the final audio, and the reason.
  - Report: measurements before and after (LUFS, true peak) per track, the number of silences and hesitations removed, the "uh"s flagged but not cut, and the opinions Claude gave.
- **Markers**: a MIDI file that contains only the markers, and the same markers written into the mix WAV. Logic Pro and Cakewalk can read one or the other; the right format is to be confirmed by testing in each application.

All analysis runs on the original audio. The program keeps the cut map to remap every timecode onto the final file.

## Out of scope, decisions and open questions

The first version does not do the creative editing (choice of clips, order of sequences, sound design) nor the publication of the episode. Nor does it separate two voices recorded together.

| Topic | Decision |
| --- | --- |
| Recording | Always two people, plus the film track on its own: one track per person, or one stereo track holding both voices |
| Raw format | WAV only, at the best recording quality |
| Episode length | About 2 h 10 |
| Film clips | Played live during the recording, on a separate track |
| Editing software | Logic Pro |
| Sound reference | Several raw episodes with their Auphonic-processed version |
| Style reference | Several dozen hours of edited episodes, with their raw recordings without the film clips |
| Overlaps | Timecode only, no automatic volume reduction; no detection with mixed voices |
| Output file | A single .md per episode: timecodes and report |
| Access to Claude | Built-in account: the logged-in Claude Code CLI, with the subscription; never an API key. The transcript may be sent to it |
| Program language | English: messages, errors, help, edit file, configuration keys. Voice markers stay sentences spoken in French |
| Documentation language | English (`name.md`) and French (`name.fr.md`), updated together; this specification's French version is the reference |

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
- **Quick test**: runs the whole chain on a 10-minute excerpt of the voice tracks and the film track, to check a change without processing 2 h 10.
- **Windows compatibility**: checks paths, the presence of ffmpeg and file encoding before each release.

A `CLAUDE.md` file at the root restates the decisions of this document and the repository rules. Claude Code reads it at the start of each session.

Sources: [Dupple, best Claude Code skills 2026](https://dupple.com/learn/best-claude-code-skills-2026) · [Redwerk, best Claude Code plugins 2026](https://redwerk.com/blog/best-claude-code-plugins/)
