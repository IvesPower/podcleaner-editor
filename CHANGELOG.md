# Changelog

[Français](CHANGELOG.fr.md) · **English**

All notable changes to podcleaner-editor. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Studio sound in `pedit run`: each voice track goes through DeepFilterNet 3 (noise and reverb), then ffmpeg filters (high-pass, EQ, compressor); the film gets its own gain to the voices' loudness, and one gain shared by every track and the mix brings the mix to -16 LUFS without passing -1 dBTP. The edit file has a `### Sound` section (chain, film gain, shared gain, loudness and true peak of each file before and after). The `[sound]` configuration section sets it (`enabled`, `denoise`, `filters`, `target_lufs`, `true_peak_db`). The DeepFilterNet model is downloaded on the first run.
- A slow test on the test recording: mix loudness and true peak, and band balance against the Auphonic version.
- `pedit run` without `--dry-run` writes the edited audio: one track per voice (or the mixed voices track) and the film track, cut at the same samples with an equal-power crossfade (30 ms) at every join, a stereo mix, and the markers in a MIDI file and in the mix WAV, each named by its type only (`Requested cut`, `Clip to add`, `Film clip`, `Overlap`, `Hesitation` for a "euh" that could not be cut). The edit file lists the files written and its "Final" timecodes match the audio.
- A gate on each voice track, like Logic Pro's Strip Silence (-30 dB, 0.5 s, 10 ms attack, 0.1 s release), decided on sound level with the bleed test; the `[gate]` section of the configuration sets it or turns it off.
- Safe writing: files are written under a temporary name then renamed, never left half-written after an error; the disk space is checked first, and tracks with different rates or more than 2 channels stop the run with a clear error.
- `pedit run --dry-run` now transcribes the passages where someone speaks (Whisper: mlx-whisper on Apple silicon, faster-whisper elsewhere; the model, about 1.6 GB, is downloaded on the first run) and keeps the words in `<name>.words.json`, so a second run does not transcribe again.
- Hesitations: every isolated "euh" is removed, the others (another voice or word at the same time, a film clip, too long) are flagged in the edit file with the words around them.
- Voice markers: a spoken instruction to Claude (a call at the start of a sentence, "dis Claude" or "Claude" followed by a comma or a pause, then an action word such as "couper" or "ajouter") becomes a `Requested cut` or `Clip to add` event and a marker; the instruction stays in the audio, to be cut by hand (`[markers] cut_instructions = true` cuts it when nobody else speaks over it).
- The edit file's report now has the hesitations, the markers and the transcription (engine, speech transcribed, tracks read from the cache).
- `pedit run --dry-run`: reads an episode (one WAV per voice, or both voices on one stereo WAV, plus the film track) and writes its edit file: film clips, attempts to talk over the other person (separate tracks only), long silences to shorten, with timecodes on the original and on the edited audio.
- `pedit init`: a few questions (output folder, recording layout, speakers' names, Claude), then the commented configuration file; `pedit config` shows it.
- Pixel-art title in the podcast's colours at the start of the tool in a terminal.
- Specification, roadmap and the plans of milestones 1 and 2, in English and French.
- Repository rules: protected `main`, pull requests approved by the maintainer, Conventional Commits in English then French.

### Changed

- Python 3.11 only (`>=3.11,<3.12`): DeepFilterNet has no package for 3.12 on Apple silicon. CI no longer tests 3.12.
