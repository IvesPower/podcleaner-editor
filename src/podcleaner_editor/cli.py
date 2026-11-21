import sys
from typing import Annotated

import typer

from podcleaner_editor import __version__, prog_name
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
