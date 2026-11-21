# Contributing

[Français](CONTRIBUTING.fr.md) · **English**

## Workflow

- `main` is protected: nobody pushes to it directly, and force-pushes and deletion are blocked.
- Every change goes through a pull request. A PR is merged only after the maintainer approves it (see [CODEOWNERS](.github/CODEOWNERS)).
- Work on a branch named after its type: `feat/silence-detection`, `fix/track-loading`, `docs/readme`.

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/), written **in English, then in French**, so that everyone can read the history:

```
<type>(<optional scope>): <English summary> / <résumé en français>
```

An optional body has one paragraph in English, a blank line, then the same paragraph in French.

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`. A breaking change adds `!` after the type (`feat!: …`) or a `BREAKING CHANGE:` footer.

Examples:

```
feat(silences): shorten long silences to 0.4 s / raccourcir les longs blancs à 0,4 s
fix(cli): exit with code 2 when ffmpeg is missing / sortir avec le code 2 quand ffmpeg manque
docs: translate the roadmap / traduire la feuille de route
```

## Pull request title and description

- The **title** uses the same format as a commit title: `type: English / français`.
- The **description** is written entirely in English first, then entirely in French, separated by `---`.
- Each language starts with a **TL;DR**: 1 to 3 plain sentences saying what the PR changes and why, understandable without reading the code.

The [PR template](.github/pull_request_template.md) is filled in automatically when you open a PR.

## Code

Everything in the code is in English: identifiers, comments, docstrings, assertion messages, comments in configuration files. The program's output is in English too: messages, errors, CLI help, logs, the edit file and the configuration keys.

The code runs on macOS and Windows: use `pathlib`, never a hard-coded path, and write text files with `encoding="utf-8"`.

## Documentation

Docs exist in English and French. English files have no suffix (`README.md`), French files end in `.fr.md` (`README.fr.md`). When you change one, update the other in the same PR, or say in the PR that the translation is pending. The specification was written in French: [`docs/spec.fr.md`](docs/spec.fr.md) is the reference, [`docs/spec.md`](docs/spec.md) its translation.

## Working with Claude Code (graphify)

The repository ships a [graphify](https://github.com/Graphify-Labs/graphify) setup for Claude Code: a knowledge graph of the code that Claude queries instead of re-reading files, which keeps each session's context smaller. The code is parsed locally with tree-sitter; nothing is sent over the network.

```bash
uv tool install graphifyy    # once per machine (the package name has two y's)
graphify update .            # build or refresh the graph in graphify-out/ (not committed)
graphify hook install        # optional: rebuild the graph after each commit and checkout
```

The Claude Code hooks in `.claude/settings.json` call `graphify`: without it installed, Claude Code shows a non-blocking hook error and works as usual.

## Before opening a PR

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```

All must pass on macOS and Windows; CI checks both. New behaviour comes with tests written first.
