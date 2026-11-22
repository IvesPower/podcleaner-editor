# Changelog

[Français](CHANGELOG.fr.md) · **English**

All notable changes to podcleaner-editor. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `pedit run --dry-run` now transcribes the passages where someone speaks (Whisper: mlx-whisper on Apple silicon, faster-whisper elsewhere; the model, about 1.6 GB, is downloaded on the first run) and keeps the words in `<name>.words.json`, so a second run does not transcribe again.
- Hesitations: every isolated "euh" is removed, the others (another voice or word at the same time, a film clip, too long) are flagged in the edit file with the words around them.
- Voice markers: a spoken instruction to Claude (a sentence that starts with "Claude" or "dis Claude" and holds an action word such as "couper" or "ajouter") becomes a `Requested cut` or `Clip to add` event, and the instruction itself is removed when nobody else speaks over it.
- The edit file's report now has the hesitations, the markers and the transcription (engine, speech transcribed, tracks read from the cache).
- `pedit run --dry-run`: reads an episode (one WAV per voice, or both voices on one stereo WAV, plus the film track) and writes its edit file: film clips, attempts to talk over the other person (separate tracks only), long silences to shorten, with timecodes on the original and on the edited audio.
- `pedit init`: a few questions (output folder, recording layout, speakers' names, Claude), then the commented configuration file; `pedit config` shows it.
- Pixel-art title in the podcast's colours at the start of the tool in a terminal.
- Specification, roadmap and the plans of milestones 1 and 2, in English and French.
- Repository rules: protected `main`, pull requests approved by the maintainer, Conventional Commits in English then French.
