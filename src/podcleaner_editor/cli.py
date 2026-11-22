import sys
from pathlib import Path
from typing import Annotated

import typer

from podcleaner_editor import __version__, config, pipeline, prog_name
from podcleaner_editor.audio_io import require_ffmpeg
from podcleaner_editor.episode import load_episode
from podcleaner_editor.errors import EditorError

app = typer.Typer(
    help="Do the repetitive part of editing a podcast episode.",
    invoke_without_command=True,
    pretty_exceptions_enable=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    _version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
) -> None:
    """Do the repetitive part of editing a podcast episode."""
    if ctx.invoked_subcommand is None:  # the command alone: its help, not an error
        typer.echo(ctx.get_help())


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help=f"Configuration file (else {config.CONFIG_ENV_VAR}, then the usual location).",
    ),
]


def _output_dir(out: Path | None, name: str | None, settings: config.Settings) -> tuple[Path, str]:
    """Where the episode's files go, and the episode's name."""
    if out is not None:
        return out, name or out.name
    if not name:
        raise EditorError("Give the episode a --name, or choose the folder with --out.")
    if settings.output_dir is None:
        raise EditorError(f"No output folder: pass --out, or set one with `{prog_name()} init`.")
    return settings.output_dir / name, name


@app.command("run")
def run_command(
    voices: Annotated[
        list[Path],
        typer.Option(
            "--voice",
            help="Voice track (WAV). Twice: one file per voice. Once: both voices on one file.",
        ),
    ],
    film: Annotated[Path, typer.Option("--film", help="Film track (WAV).")],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Folder for this episode's files (else output_dir/<name>)."),
    ] = None,
    name: Annotated[
        str | None, typer.Option("--name", help="Episode name (else the --out folder name).")
    ] = None,
    config_path: ConfigOption = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Write the edit file only, no audio.")
    ] = False,
) -> None:
    """Analyse an episode and write its edit file."""
    settings = config.load_settings(config.resolve_config_path(config_path))
    out_dir, episode_name = _output_dir(out, name, settings)
    if not dry_run:
        raise EditorError(
            "Writing the edited audio comes in a later version; run again with --dry-run."
        )
    require_ffmpeg()
    ep = load_episode(voices, film, episode_name, settings)
    if ep.layout != settings.layout:
        typer.echo(
            f"⚠ {len(voices)} voice file(s) given: treated as the {ep.layout} layout "
            f"(the configuration says {settings.layout})."
        )
    path = pipeline.run(ep, settings, out_dir, progress=typer.echo)
    typer.echo(f"Edit file written: {path}")


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(__version__)


def main() -> None:
    # Click standalone mode handles usage errors itself (exit code 2);
    # EditorError is not a Click exception, so it propagates up to here.
    try:
        app(prog_name=prog_name())
    except EditorError as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(2)
