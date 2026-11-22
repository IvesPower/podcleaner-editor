"""Claude through the built-in account: the Claude Code CLI, logged in with a subscription.

Never an API key: the CLI runs without ANTHROPIC_API_KEY in its environment, from a
temporary folder (no CLAUDE.md read). M1 only checks that the CLI is there and logged in;
the questions to Claude come in M5, launched as in podcleaner-clips.
"""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

# Runs a command: (args, stdin text, timeout) → completed process (text output).
Runner = Callable[[list[str], str, float], subprocess.CompletedProcess]


def run_cli(args: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # the CLI must use the subscription, not a key
    with tempfile.TemporaryDirectory(prefix="podcleaner-editor-") as cwd:
        return subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=False,
        )


def find_cli() -> str | None:
    """Path of the Claude Code CLI (`claude`, `claude.exe` or `claude.cmd`), if installed.

    Looks in PATH, then where the Claude Code installers put it: the terminal that runs this
    tool does not always have that folder in its PATH.
    """
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for folder in (home / ".local" / "bin", home / ".claude" / "local"):
        found = shutil.which("claude", path=str(folder))
        if found:
            return found
    return None


def cli_logged_in(cli: str, runner: Runner = run_cli) -> bool | None:
    """True or False from `claude auth status`; None if it cannot tell."""
    try:
        done = runner([cli, "auth", "status", "--json"], "", 30)
        return bool(json.loads(done.stdout)["loggedIn"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
