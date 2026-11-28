import subprocess
import sys

from typer.testing import CliRunner

from podcleaner_editor import pipeline
from podcleaner_editor.cli import app


def _run_main(*body: str) -> subprocess.CompletedProcess:
    """Runs the real main() entry point in a subprocess, after the given setup lines."""
    script = "\n".join(["from podcleaner_editor.cli import app, main", *body, "main()", ""])
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, encoding="utf-8"
    )


def test_version_command_prints_version():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_version_option():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


def test_command_alone_prints_help():
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 0
    assert "version" in result.output


def test_editor_error_exits_2_with_message():
    proc = _run_main(
        "from podcleaner_editor.errors import EditorError",
        "@app.command('boom')",
        "def boom():",
        "    raise EditorError('File not found: x.wav')",
        "import sys; sys.argv = ['pedit', 'boom']",
    )
    assert proc.returncode == 2
    assert "Error: File not found: x.wav" in proc.stderr
    assert "Traceback" not in proc.stdout + proc.stderr


def test_unknown_command_is_a_usage_error_without_traceback():
    proc = _run_main("import sys; sys.argv = ['pedit', 'nope']")
    assert proc.returncode == 2
    assert "nope" in proc.stderr
    assert "Traceback" not in proc.stdout + proc.stderr


def test_cli_run_without_dry_run(make_wav, tmp_path, monkeypatch):
    a = make_wav(tmp_path / "a.wav", seconds=5, sr=8000, signal="tone")
    b = make_wav(tmp_path / "b.wav", seconds=5, sr=8000, signal="tone")
    film = make_wav(tmp_path / "film.wav", seconds=5, sr=8000)
    monkeypatch.setattr(pipeline, "speech_intervals", lambda samples, settings: [])
    out = tmp_path / "ep"
    args = ["run", "--voice", a, "--voice", b, "--film", film, "--out", out]
    result = CliRunner().invoke(app, [str(arg) for arg in args])
    assert result.exit_code == 0, result.output
    assert result.output.count("Written: ") >= 4
    for name in ("ep.edit.md", "ep.mix.wav", "ep.film.wav", "ep.markers.mid"):
        assert f"Written: {out / name}" in result.output
    assert "Writing the edited tracks…" in result.output
