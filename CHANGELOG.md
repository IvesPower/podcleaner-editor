# Changelog

[Français](CHANGELOG.fr.md) · **English**

All notable changes to podcleaner-editor. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `pedit run --dry-run`: reads an episode (one WAV per voice, or both voices on one stereo WAV, plus the film track) and writes its edit file: film clips, attempts to talk over the other person (separate tracks only), long silences to shorten, with timecodes on the original and on the edited audio.
- `pedit init`: a few questions (output folder, recording layout, speakers' names, Claude), then the commented configuration file; `pedit config` shows it.
- Pixel-art title in the podcast's colours at the start of the tool in a terminal.
- Specification, roadmap and milestone 1 plan, in English and French.
- Repository rules: protected `main`, pull requests approved by the maintainer, Conventional Commits in English then French.
