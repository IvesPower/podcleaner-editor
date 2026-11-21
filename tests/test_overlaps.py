from podcleaner_editor.config import Settings
from podcleaner_editor.detect.overlaps import find_overlap_attempts
from podcleaner_editor.events import Event, EventType
from podcleaner_editor.timeline import Interval as I

S = Settings()


def _find(a, b):
    return find_overlap_attempts(a, b, "Julien", "Marc", S)


def test_attempt_flagged():
    events = _find([I(0, 20)], [I(5, 6)])
    assert events == [
        Event(
            type=EventType.OVERLAP,
            start=5,
            end=6,
            track="Marc",
            reason="Marc tries to speak while Julien is speaking; Julien keeps the floor",
        )
    ]
    assert events[0].source == "rule"


def test_short_backchannel_ignored():
    assert _find([I(0, 20)], [I(5, 5.3)]) == []


def test_turn_taking_not_flagged():
    assert _find([I(0, 10)], [I(9.5, 20)]) == []


def test_symmetric():
    events = _find([I(5, 6)], [I(0, 20)])
    assert [(e.track, e.start, e.end) for e in events] == [("Julien", 5, 6)]
    assert events[0].reason.startswith("Julien tries to speak while Marc is speaking")


def test_brief_pause_in_a_still_counts_as_holding_floor():
    assert len(_find([I(0, 6), I(6.2, 20)], [I(5, 6)])) == 1


def test_starting_together_is_not_an_attempt():
    assert _find([I(0, 20)], [I(0, 1)]) == []


def test_events_are_sorted_by_start():
    events = _find([I(0, 20), I(30, 50)], [I(5, 6), I(35, 36)] + [I(25, 26)])
    assert [e.start for e in events] == [5, 35]
    both = _find([I(0, 20), I(42, 43)], [I(10, 11), I(40, 60)])
    assert [(e.track, e.start) for e in both] == [("Marc", 10), ("Julien", 42)]


def test_event_types_read_in_english():
    assert EventType.FILM_CLIP == "Film clip"
    assert EventType.CUT_REQUEST == "Requested cut"
