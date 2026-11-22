import os

import pytest

from podcleaner_editor import __version__, banner


def test_pixel_lines_have_the_same_width():
    lines = banner.pixel_lines()
    assert len(lines) == 4
    assert len({len(line) for line in lines}) == 1
    assert set("".join(lines)) <= set("█▀▄ ")


def test_every_letter_of_the_name_is_in_the_font():
    assert set(banner.NAME) <= set(banner._FONT)


def _size(columns):
    return lambda: os.terminal_size((columns, 40))


@pytest.fixture
def terminal(monkeypatch, capsys):
    """Output that says it is a terminal; read it with capsys (pytest owns sys.stdout)."""
    monkeypatch.setattr(banner, "_stdout_is_tty", lambda: True)
    monkeypatch.delenv(banner.NO_BANNER_ENV_VAR, raising=False)
    return capsys


def test_banner_shown_in_a_terminal(terminal, monkeypatch):
    monkeypatch.setattr(banner.shutil, "get_terminal_size", _size(120))
    banner.show(None)
    text = terminal.readouterr().out
    assert "█" in text and f"v{__version__}" in text


def test_banner_hidden_outside_a_terminal(capsys):
    banner.show(None)
    assert capsys.readouterr().out == ""


def test_banner_hidden_by_env_var(terminal, monkeypatch):
    monkeypatch.setenv(banner.NO_BANNER_ENV_VAR, "1")
    banner.show(None)
    assert terminal.readouterr().out == ""


def test_banner_falls_back_to_one_line_when_narrow(terminal, monkeypatch):
    monkeypatch.setattr(banner.shutil, "get_terminal_size", _size(40))
    banner.show(None)
    text = terminal.readouterr().out
    assert "█" not in text
    assert text.startswith(f"podcleaner-editor {__version__} - ")
