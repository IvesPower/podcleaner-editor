import numpy as np
import soundfile as sf

from podcleaner_editor.render import markers as markers_module
from podcleaner_editor.render.markers import (
    Marker,
    add_wav_markers,
    read_wav_markers,
    write_midi,
)

UNICODE_NAME = 'Requested cut: Spoken instruction: "dis Claude, on coupe « ça » | là"'


def _read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def _midi_events(data: bytes) -> list[tuple[int, bytes]]:
    """(tick, text) of each marker event, after checking the header and the end."""
    assert data[:14] == b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x03\xc0"
    assert data[14:18] == b"MTrk"
    length = int.from_bytes(data[18:22], "big")
    track = data[22:]
    assert len(track) == length
    assert track[:7] == b"\x00\xff\x51\x03\x07\xa1\x20"
    assert track.endswith(b"\x00\xff\x2f\x00")
    pos, tick, events = 7, 0, []
    while pos < len(track) - 4:
        delta, pos = _read_vlq(track, pos)
        tick += delta
        assert track[pos : pos + 2] == b"\xff\x06"
        size, pos = _read_vlq(track, pos + 2)
        events.append((tick, track[pos : pos + size]))
        pos += size
    return events


def test_midi_bytes(tmp_path):
    path = tmp_path / "m.mid"
    write_midi([Marker(1.0, "B"), Marker(0.5, "A")], path)
    data = path.read_bytes()
    track = data[22:]
    assert track == (
        b"\x00\xff\x51\x03\x07\xa1\x20"
        b"\x87\x40\xff\x06\x01A"  # delta 960
        b"\x87\x40\xff\x06\x01B"  # delta 960
        b"\x00\xff\x2f\x00"
    )
    assert _midi_events(data) == [(960, b"A"), (1920, b"B")]
    assert not path.with_name("m.mid.tmp").exists()


def test_midi_vlq_for_long_times(tmp_path):
    path = tmp_path / "m.mid"
    write_midi([Marker(7200.0, "late")], path)
    assert _midi_events(path.read_bytes()) == [(13_824_000, b"late")]


def test_wav_markers_round_trip(tmp_path):
    path = tmp_path / "mix.wav"
    audio = np.random.default_rng(0).uniform(-0.5, 0.5, (44100, 2)).astype(np.float32)
    sf.write(path, audio, 44100, subtype="FLOAT")
    assert add_wav_markers(path, [Marker(0.5, "Clip to add: x")], 44100) is True
    assert read_wav_markers(path) == [(22050, "Clip to add: x")]
    back, rate = sf.read(path, dtype="float32")
    assert rate == 44100
    np.testing.assert_array_equal(back, audio)
    data = path.read_bytes()
    assert int.from_bytes(data[4:8], "little") == len(data) - 8


def test_wav_markers_odd_names_and_order(tmp_path):
    path = tmp_path / "mix.wav"
    sf.write(path, np.zeros((100, 2), dtype=np.float32), 100, subtype="FLOAT")
    markers = [Marker(0.9, "abc"), Marker(0.1, "ab")]
    assert add_wav_markers(path, markers, 100)
    assert read_wav_markers(path) == [(10, "ab"), (90, "abc")]
    assert add_wav_markers(path, [], 100) is True


def test_wav_empty_list_writes_nothing(tmp_path):
    path = tmp_path / "mix.wav"
    sf.write(path, np.zeros((100, 2), dtype=np.float32), 100, subtype="FLOAT")
    before = path.read_bytes()
    assert add_wav_markers(path, [], 100) is True
    assert path.read_bytes() == before


def test_rf64_is_left_untouched(tmp_path):
    path = tmp_path / "big.wav"
    path.write_bytes(b"RF64" + b"\xff" * 4 + b"WAVE" + b"\x00" * 20)
    before = path.read_bytes()
    assert add_wav_markers(path, [Marker(1.0, "x")], 100) is False
    assert path.read_bytes() == before


def test_wav_markers_left_out_past_the_wav_size_limit(tmp_path, monkeypatch):
    path = tmp_path / "mix.wav"
    sf.write(path, np.zeros((100, 2), dtype=np.float32), 100, subtype="FLOAT")
    before = path.read_bytes()
    # The markers would push the RIFF size past what a plain WAV can declare.
    monkeypatch.setattr(markers_module, "_WAV_LIMIT", len(before))
    assert add_wav_markers(path, [Marker(0.5, "x")], 100) is False
    assert path.read_bytes() == before


def test_vlq_of_a_negative_value_is_zero():
    assert markers_module._vlq(-1) == markers_module._vlq(0) == b"\x00"
    assert markers_module._vlq(200) == b"\x81\x48"


def test_unicode_names_round_trip(tmp_path):
    midi = tmp_path / "m.mid"
    write_midi([Marker(2.0, UNICODE_NAME)], midi)
    assert _midi_events(midi.read_bytes()) == [(3840, UNICODE_NAME.encode("utf-8"))]
    wav = tmp_path / "mix.wav"
    sf.write(wav, np.zeros((100, 2), dtype=np.float32), 100, subtype="FLOAT")
    add_wav_markers(wav, [Marker(2.0, UNICODE_NAME)], 100)
    assert read_wav_markers(wav) == [(200, UNICODE_NAME)]
