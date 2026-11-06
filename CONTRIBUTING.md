# Contributing

*[Version française](CONTRIBUTING.fr.md)*

Thanks for your interest in PodCleaner-editor. Contributions are welcome through pull requests.

## How changes get in

- Nobody pushes to `main` directly. Every change goes through a pull request.
- Fork the repository (or create a branch if you have access), make your change, and open a pull request against `main`.
- The repository owner reviews and approves every pull request before it is merged.
- Pull requests are merged with **squash and merge**, so the pull request title becomes the commit message on `main`. It must follow the convention below.

## Commit convention

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>): <short description>
```

| Type | Use it for |
| --- | --- |
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `build` | Packaging, dependencies |
| `ci` | Continuous integration |
| `chore` | Anything else (tooling, housekeeping) |

Examples: `feat(silences): shorten long silences to 0.4 s`, `fix(cli): exit with code 2 when ffmpeg is missing`, `docs: translate the roadmap`.

A breaking change adds `!` after the type (`feat!: …`) and a `BREAKING CHANGE:` footer.

Commit messages are written in English.

## Branch names

`<type>/<short-description>`, for example `feat/film-clip-detection` or `docs/readme-install`.

## Before opening a pull request

- Tests pass: `uv run pytest` (and `uv run pytest -m slow` if you touched model code).
- Lint passes: `uv run ruff check` and `uv run ruff format --check`.
- New behaviour comes with tests written first.
- The code runs on macOS and Windows: use `pathlib`, and write text files with `encoding="utf-8"`.

## Documentation

Documentation exists in English and French. English is the default (`name.md`), French sits next to it (`name.fr.md`). If you change one, update the other in the same pull request, or say in the pull request that the translation is missing so someone can add it.
