import subprocess

from podcleaner_editor import claude_cli


def _runner(stdout: str):
    def run(args, stdin, timeout):
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    return run


def test_cli_logged_in_reads_json():
    assert claude_cli.cli_logged_in("claude", _runner('{"loggedIn": true}')) is True
    assert claude_cli.cli_logged_in("claude", _runner('{"loggedIn": false}')) is False
    assert claude_cli.cli_logged_in("claude", _runner("not json")) is None


def test_cli_logged_in_when_the_command_fails():
    def broken(args, stdin, timeout):
        raise OSError("no such file")

    assert claude_cli.cli_logged_in("claude", broken) is None


def test_find_cli_looks_outside_path(monkeypatch, tmp_path):
    folder = tmp_path / ".local" / "bin"
    monkeypatch.setattr(claude_cli.Path, "home", lambda: tmp_path)

    def which(name, path=None):
        return str(folder / name) if path == str(folder) else None

    monkeypatch.setattr(claude_cli.shutil, "which", which)
    assert claude_cli.find_cli() == str(folder / "claude")


def test_find_cli_none(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_cli.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda name, path=None: None)
    assert claude_cli.find_cli() is None


def test_the_cli_never_gets_the_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    claude_cli.run_cli(["claude", "auth", "status"], "", 5)
    assert "ANTHROPIC_API_KEY" not in seen["env"]
