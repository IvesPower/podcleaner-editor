# Changelog

[Français](CHANGELOG.fr.md) · **English**

All notable changes to podcleaner-editor. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `pedit run` without `--dry-run` writes the edited audio: one track per voice (or the mixed voices track) and the film track, cut at the same samples with an equal-power crossfade (30 ms) at every join, a stereo mix, and the markers in a MIDI file and in the mix WAV. The edit file lists the files written and its "Final" timecodes match the audio.
- A gate on each voice track, like Logic Pro's Strip Silence (-30 dB, 0.5 s, 10 ms attack, 0.1 s release), decided on sound level with the bleed test; the `[gate]` section of the configuration sets it or turns it off.
- Safe writing: files are written under a temporary name then renamed, never left half-written after an error; the disk space is checked first, and tracks with different rates or more than 2 channels stop the run with a clear error.
- `pedit run --dry-run` now transcribes the passages where someone speaks (Whisper: mlx-whisper on Apple silicon, faster-whisper elsewhere; the model, about 1.6 GB, is downloaded on the first run) and keeps the words in `<name>.words.json`, so a second run does not transcribe again.
- Hesitations: every isolated "euh" is removed, the others (another voice or word at the same time, a film clip, too long) are flagged in the edit file with the words around them.
- Voice markers: a spoken instruction to Claude (a call at the start of a sentence, "dis Claude" or "Claude" followed by a comma or a pause, then an action word such as "couper" or "ajouter") becomes a `Requested cut` or `Clip to add` event, and the instruction itself is removed when nobody else speaks over it; one with no clear end within 15 s is kept in the audio.
- The edit file's report now has the hesitations, the markers and the transcription (engine, speech transcribed, tracks read from the cache).
- `pedit run --dry-run`: reads an episode (one WAV per voice, or both voices on one stereo WAV, plus the film track) and writes its edit file: film clips, attempts to talk over the other person (separate tracks only), long silences to shorten, with timecodes on the original and on the edited audio.
- `pedit init`: a few questions (output folder, recording layout, speakers' names, Claude), then the commented configuration file; `pedit config` shows it.
- Pixel-art title in the podcast's colours at the start of the tool in a terminal.
- Specification, roadmap and the plans of milestones 1 and 2, in English and French.
- Repository rules: protected `main`, pull requests approved by the maintainer, Conventional Commits in English then French.
