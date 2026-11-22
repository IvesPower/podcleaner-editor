from pathlib import Path

import pytest
from typer.testing import CliRunner

from podcleaner_editor import cli, config, wizard
from podcleaner_editor.config import Settings, load_settings, render_template, settings_values


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(wizard.claude_cli, "find_cli", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(wizard.claude_cli, "cli_logged_in", lambda c: True)


def _init(path: Path, answers: str, *extra: str):
    return CliRunner().invoke(cli.app, ["init", "--config", str(path), *extra], input=answers)


def test_wizard_writes_answers(tmp_path, interactive):
    out, path = tmp_path / "Episodes", tmp_path / "config.toml"
    result = _init(path, f"{out}\ny\nmixed\nJulien\nFranck\ny\n")
    assert result.exit_code == 0, result.output
    s = load_settings(path)
    assert s.output_dir == out and out.is_dir()
    assert s.layout == "mixed"
    assert s.speakers == ("Julien", "Franck")
    assert s.claude_enabled is True
    assert f"Configuration saved: {path}" in result.output


def test_wizard_offers_current_values(tmp_path, interactive):
    out, path = tmp_path / "Episodes", tmp_path / "config.toml"
    out.mkdir()
    _init(path, f"{out}\nmixed\nJulien\nFranck\nn\n")
    result = _init(path, "\n\n\n\n\ny\n")  # Enter keeps each value, then confirm replacing
    assert result.exit_code == 0, result.output
    s = load_settings(path)
    assert (s.output_dir, s.layout, s.speakers, s.claude_enabled) == (
        out,
        "mixed",
        ("Julien", "Franck"),
        False,
    )


def test_wizard_rejects_an_unknown_layout(tmp_path, interactive):
    out, path = tmp_path / "Episodes", tmp_path / "config.toml"
    out.mkdir()
    result = _init(path, f"{out}\nstereo\nseparate\nJulien\nFranck\ny\n")
    assert result.exit_code == 0, result.output
    assert "Answer separate or mixed." in result.output
    assert load_settings(path).layout == "separate"


def test_wizard_keeps_file_when_replace_refused(tmp_path, interactive):
    out, path = tmp_path / "Episodes", tmp_path / "config.toml"
    out.mkdir()
    path.write_text("[silences]\ntarget_s = 0.6\n", encoding="utf-8")
    result = _init(path, f"{out}\nseparate\nJulien\nFranck\ny\nn\n")
    assert result.exit_code == 1
    assert "Nothing was written." in result.output
    assert path.read_text(encoding="utf-8") == "[silences]\ntarget_s = 0.6\n"


def test_wizard_keeps_settings_it_does_not_ask(tmp_path, interactive):
    out, path = tmp_path / "Episodes", tmp_path / "config.toml"
    out.mkdir()
    path.write_text("[silences]\ntarget_s = 0.6\n", encoding="utf-8")
    _init(path, f"{out}\nseparate\nJulien\nFranck\ny\ny\n")
    assert load_settings(path).silence_target_s == 0.6


def test_wizard_warns_when_claude_code_is_missing(tmp_path, interactive, monkeypatch):
    monkeypatch.setattr(wizard.claude_cli, "find_cli", lambda: None)
    out = tmp_path / "Episodes"
    out.mkdir()
    result = _init(tmp_path / "config.toml", f"{out}\nseparate\nJulien\nFranck\ny\n")
    assert "Claude Code is not installed" in result.output


def test_wizard_warns_when_claude_code_is_logged_out(tmp_path, interactive, monkeypatch):
    monkeypatch.setattr(wizard.claude_cli, "cli_logged_in", lambda c: False)
    out = tmp_path / "Episodes"
    out.mkdir()
    result = _init(tmp_path / "config.toml", f"{out}\nseparate\nJulien\nFranck\ny\n")
    assert "claude auth login" in result.output


def test_init_no_input_writes_template(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    result = _init(path, "", "--no-input")
    assert result.exit_code == 0, result.output
    assert path.read_text(encoding="utf-8") == render_template(settings_values(Settings()))


def test_init_outside_a_terminal_asks_nothing(tmp_path):
    path = tmp_path / "config.toml"
    result = _init(path, "")
    assert result.exit_code == 0, result.output
    assert load_settings(path) == Settings()


def test_init_no_input_keeps_an_existing_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[silences]\ntarget_s = 0.6\n", encoding="utf-8")
    result = _init(path, "", "--no-input")
    assert result.exception is not None and "already exists" in str(result.exception)
    assert load_settings(path).silence_target_s == 0.6


@pytest.mark.parametrize(
    ("typed", "windows", "expected"),
    [
        ("'/Users/me/My Episodes'", False, "/Users/me/My Episodes"),
        ('"C:\\Podcast\\Episodes"', True, "C:\\Podcast\\Episodes"),
        ("/Users/me/My\\ Episodes ", False, "/Users/me/My Episodes"),
        ("C:\\Podcast\\Episodes", True, "C:\\Podcast\\Episodes"),
    ],
)
def test_clean_path_strips_quotes_and_escapes(typed, windows, expected):
    assert wizard.clean_path(typed, windows=windows) == expected


def test_write_config_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text("old\n", encoding="utf-8")

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(config.os, "replace", broken_replace)
    with pytest.raises(OSError):
        config.write_config(path, "new\n")
    assert path.read_text(encoding="utf-8") == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_config_path_option(tmp_path):
    path = tmp_path / "config.toml"
    result = CliRunner().invoke(cli.app, ["config", "--path", "--config", str(path)])
    assert result.exit_code == 0
    assert result.output.strip() == str(path)


def test_config_shows_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[recording]\nlayout = "mixed"\n', encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["config", "--config", str(path)])
    assert result.exit_code == 0
    assert f"File: {path}" in result.output
    assert "recording.layout = mixed" in result.output
    assert "silences.min_s = 1.0" in result.output
