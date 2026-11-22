"""`init`: questions in the console that write the configuration file."""

import os
import re
from dataclasses import replace
from pathlib import Path

import typer

from podcleaner_editor import claude_cli, config, prog_name
from podcleaner_editor.errors import EditorError

_SHELL_ESCAPE = re.compile(r"\\(.)")  # macOS Terminal escapes a dragged path: My\ Folder


def clean_path(text: str, *, windows: bool = os.name == "nt") -> str:
    """A path as pasted or dragged into the terminal: no quotes around it, no shell escapes."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    elif not windows:
        text = _SHELL_ESCAPE.sub(r"\1", text)
    return text


def _absolute(text: str) -> Path:
    path = Path(clean_path(text)).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _current(path: Path) -> config.Settings:
    """The current file's settings, so that each question offers them as its default."""
    try:
        return config.load_settings(path)
    except EditorError as exc:
        typer.echo(f"⚠ The current file cannot be read ({exc}); starting from the defaults.")
        return config.Settings()


def _ask_output_dir(current: Path | None) -> Path:
    while True:
        answer = typer.prompt(
            "Folder for the edited episodes (one subfolder per episode)",
            default=str(current) if current else None,
        )
        path = _absolute(answer)
        if path.is_dir():
            return path
        if path.exists():
            typer.echo(f"{path} is a file, not a folder.")
            continue
        if typer.confirm(f"{path} does not exist. Create it?", default=True):
            path.mkdir(parents=True)
        return path


def _ask_layout(current: str) -> config.Layout:
    typer.echo("How are your episodes recorded?")
    typer.echo("  separate: one WAV file per voice, plus the film track")
    typer.echo("  mixed:    one stereo WAV with both voices, plus the film track")
    while True:
        answer = typer.prompt("Recording layout", default=current).strip().lower()
        if answer in config.LAYOUTS:
            return answer  # type: ignore[return-value]
        typer.echo("Answer separate or mixed.")


def _ask_speakers(current: tuple[str, str]) -> tuple[str, str]:
    first = typer.prompt("First name of the first voice", default=current[0]).strip()
    second = typer.prompt("First name of the second voice", default=current[1]).strip()
    return (first or current[0], second or current[1])


def _claude_status() -> str:
    cli = claude_cli.find_cli()
    if cli is None:
        return (
            "Claude Code is not installed: the tool works without Claude "
            "(install it from https://claude.com/claude-code to use your subscription)."
        )
    if claude_cli.cli_logged_in(cli) is False:
        return "Claude Code is installed but not logged in (run: claude auth login)."
    return "Claude Code is installed and logged in: Claude can use your subscription."


def _ask_claude(current: bool) -> bool:
    typer.echo(
        "Claude can judge the hesitations, the overlaps and the voice markers, and suggest "
        "cuts, through your Claude subscription; without it, the tool uses fixed rules."
    )
    typer.echo(_claude_status())
    return typer.confirm("Use Claude when it is available?", default=current)


def run_wizard(path: Path) -> None:
    """Asks the questions, then writes `path` (after a confirmation if it exists)."""
    current = _current(path)
    typer.echo(f"A few questions to set up {prog_name()} (Ctrl+C to stop, nothing is written).")
    typer.echo("Paths can be pasted or dragged here; [brackets] show what Enter keeps.\n")

    answers = replace(
        current,
        output_dir=_ask_output_dir(current.output_dir),
        layout=_ask_layout(current.layout),
        speakers=_ask_speakers(current.speakers),
    )
    typer.echo("")
    answers = replace(answers, claude_enabled=_ask_claude(current.claude_enabled))

    typer.echo("")
    if path.exists() and not typer.confirm(f"Replace {path}?", default=True):
        typer.echo("Nothing was written.")
        raise typer.Exit(1)
    config.write_config(path, config.render_template(config.settings_values(answers)))

    typer.echo(f"Configuration saved: {path}")
    for key, value in config.describe(config.load_settings(path)):
        if key.split(".")[0] in ("paths", "recording", "claude"):
            typer.echo(f"  {key} = {value}")
    typer.echo("Other settings are in the file, commented. Change them there, or run init again.")
    voices = "--voice <voice A.wav> --voice <voice B.wav>"
    if answers.layout == "mixed":
        voices = "--voice <voices.wav>"
    typer.echo(f"\nNext: {prog_name()} run {voices} --film <film.wav> --name <episode> --dry-run")
