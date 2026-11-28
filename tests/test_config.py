from dataclasses import replace
from pathlib import Path

import pytest

from podcleaner_editor import config
from podcleaner_editor.config import (
    CONFIG_ENV_VAR,
    Settings,
    load_settings,
    render_template,
    resolve_config_path,
    settings_values,
)
from podcleaner_editor.errors import EditorError


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_match_spec():
    s = Settings()
    assert s.silence_min_s == 1.0
    assert s.silence_target_s == 0.4
    assert s.layout == "separate"
    assert s.output_dir is None
    assert s.speakers == ("Voice A", "Voice B")


def test_overlap_defaults_tuned_on_the_test_recording():
    # Tuned on samples/pedit (Julien, 2026-11-22): three talk-overs of 0.17 to 0.6 s.
    s = Settings()
    assert (s.overlap_min_s, s.overlap_floor_hold_s, s.overlap_merge_gap_s) == (0.15, 0.5, 0.5)
    assert s.own_speech_gap_s == 0.2


def test_own_speech_gap_is_read_from_levels(tmp_path):
    path = _write(tmp_path / "c.toml", "[levels]\nown_speech_gap_s = 0.1\n")
    assert load_settings(path).own_speech_gap_s == 0.1


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "nope.toml") == Settings()


def test_toml_overrides_only_given_keys(tmp_path):
    path = _write(tmp_path / "c.toml", "[silences]\ntarget_s = 0.5\n")
    s = load_settings(path)
    assert s.silence_target_s == 0.5
    assert replace(s, silence_target_s=0.4) == Settings()


def test_reads_paths_speakers_and_layout(tmp_path):
    path = _write(
        tmp_path / "c.toml",
        '[paths]\noutput_dir = "~/Episodes"\n'
        '[recording]\nlayout = "mixed"\nspeakers = ["Julien", "Marc"]\n',
    )
    s = load_settings(path)
    assert s.output_dir == Path("~/Episodes").expanduser()
    assert s.layout == "mixed"
    assert s.speakers == ("Julien", "Marc")


def test_int_is_accepted_for_a_float_setting(tmp_path):
    path = _write(tmp_path / "c.toml", "[silences]\nmin_s = 2\n")
    assert load_settings(path).silence_min_s == 2.0


def test_unknown_key_raises(tmp_path):
    path = _write(tmp_path / "c.toml", "[silences]\nmax_s = 3\n")
    with pytest.raises(EditorError, match=r"\[silences\] max_s"):
        load_settings(path)


def test_unknown_section_raises(tmp_path):
    path = _write(tmp_path / "c.toml", "[audio]\nlufs = -16\n")
    with pytest.raises(EditorError, match=r"\[audio\]"):
        load_settings(path)


def test_bad_layout_raises(tmp_path):
    path = _write(tmp_path / "c.toml", '[recording]\nlayout = "stereo"\n')
    with pytest.raises(EditorError, match="separate.*mixed"):
        load_settings(path)


def test_wrong_type_raises(tmp_path):
    path = _write(tmp_path / "c.toml", '[silences]\nmin_s = "long"\n')
    with pytest.raises(EditorError, match=r"\[silences\] min_s"):
        load_settings(path)


@pytest.mark.parametrize("names", ['["Julien", "Julien"]', '["Julien", " julien "]'])
def test_speakers_must_be_two_different_names(tmp_path, names):
    path = _write(tmp_path / "c.toml", f"[recording]\nspeakers = {names}\n")
    with pytest.raises(EditorError, match=r"\[recording\] speakers must be two different names"):
        load_settings(path)


def test_speakers_must_be_two_names(tmp_path):
    path = _write(tmp_path / "c.toml", '[recording]\nspeakers = ["Julien"]\n')
    with pytest.raises(EditorError, match="two"):
        load_settings(path)


def test_invalid_toml_names_the_file(tmp_path):
    path = _write(tmp_path / "c.toml", "[silences\n")
    with pytest.raises(EditorError, match="c.toml"):
        load_settings(path)


def test_config_path_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "user_config_dir", lambda app: str(tmp_path / "user" / app))
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
    assert resolve_config_path(None) == tmp_path / "user" / "podcleaner-editor" / "config.toml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "env.toml"))
    assert resolve_config_path(None) == tmp_path / "env.toml"
    assert resolve_config_path(tmp_path / "opt.toml") == tmp_path / "opt.toml"


def test_template_round_trips(tmp_path):
    s = replace(
        Settings(),
        output_dir=tmp_path / "Épisodes",
        layout="mixed",
        speakers=("Julien", "Marc"),
        silence_target_s=0.5,
        claude_enabled=False,
    )
    path = _write(tmp_path / "c.toml", render_template(settings_values(s)))
    assert load_settings(path) == s


def test_template_of_defaults_round_trips(tmp_path):
    path = _write(tmp_path / "c.toml", render_template(settings_values(Settings())))
    assert load_settings(path) == Settings()


def test_template_comments_every_key():
    text = render_template(settings_values(Settings()))
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "=" in line and not line.startswith("#"):
            assert lines[i - 1].startswith("# "), line


def test_filler_words_read_from_toml(tmp_path):
    path = _write(tmp_path / "c.toml", '[hesitations]\nwords = ["euh", "bah"]\n')
    assert load_settings(path).filler_words == ("euh", "bah")


@pytest.mark.parametrize("words", ["[]", '["euh", 3]', '["euh", " "]', '"euh"'])
def test_filler_words_must_be_non_empty_strings(tmp_path, words):
    path = _write(tmp_path / "c.toml", f"[hesitations]\nwords = {words}\n")
    with pytest.raises(EditorError, match=r"\[hesitations\] words"):
        load_settings(path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("trigger", '"dis Claude"'),
        ("trigger", '"!?"'),
        ("cut_words", '["couper", "on coupe"]'),
        ("clip_words", '["ajoute", "mets-le"]'),
    ],
)
def test_marker_words_must_be_single_words(tmp_path, key, value):
    path = _write(tmp_path / "c.toml", f"[markers]\n{key} = {value}\n")
    with pytest.raises(
        EditorError, match=rf"\[markers\] {key} must be (a single word|single words)"
    ):
        load_settings(path)


def test_marker_words_may_carry_accents_and_case(tmp_path):
    path = _write(tmp_path / "c.toml", '[markers]\ntrigger = "Clôde,"\ncut_words = ["Supprimer"]\n')
    settings = load_settings(path)
    assert settings.marker_trigger == "Clôde," and settings.marker_cut_words == ("Supprimer",)


def test_template_round_trips_new_settings(tmp_path):
    path = _write(tmp_path / "c.toml", render_template(settings_values(Settings())))
    assert load_settings(path) == Settings()


def test_gate_settings_read_from_toml(tmp_path):
    path = _write(tmp_path / "c.toml", "[gate]\nthreshold_db = -35\nenabled = false\n")
    s = load_settings(path)
    assert s.gate_threshold_db == -35.0
    assert s.gate_enabled is False


def test_template_round_trips_gate_settings(tmp_path):
    path = _write(tmp_path / "c.toml", render_template(settings_values(Settings())))
    assert load_settings(path) == Settings()
    assert "[gate]" in path.read_text(encoding="utf-8")


def test_sound_settings_read_from_toml(tmp_path):
    path = _write(tmp_path / "c.toml", "[sound]\nenabled = false\ntarget_lufs = -18\n")
    s = load_settings(path)
    assert s.sound_enabled is False
    assert s.sound_target_lufs == -18.0


def test_sound_defaults():
    s = Settings()
    assert s.sound_enabled is True
    assert s.sound_denoise is True
    assert s.sound_target_lufs == -16.0
    assert s.sound_true_peak_db == -1.0
    assert s.sound_filters == (
        "highpass=f=100,lowshelf=f=250:g=-4,equalizer=f=500:t=q:w=1:g=-1.5,"
        "equalizer=f=2500:t=q:w=1:g=-1,highshelf=f=4500:g=-7,"
        "acompressor=threshold=-26dB:ratio=3:attack=10:release=250:makeup=2"
    )


def test_template_round_trips_sound_settings(tmp_path):
    path = _write(tmp_path / "c.toml", render_template(settings_values(Settings())))
    assert load_settings(path) == Settings()
    assert "[sound]" in path.read_text(encoding="utf-8")
