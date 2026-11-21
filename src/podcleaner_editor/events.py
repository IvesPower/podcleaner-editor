"""What the edit file lists: each event with its type, its time on the original audio, why."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class EventType(StrEnum):
    CUT_REQUEST = "Requested cut"
    CLIP_TO_ADD = "Clip to add"
    FILM_CLIP = "Film clip"
    OVERLAP = "Overlap"
    SUGGESTION = "Suggestion"


@dataclass(frozen=True)
class Event:
    type: EventType
    start: float  # seconds on the original audio
    end: float
    track: str  # label of the track it happened on
    reason: str
    source: Literal["rule", "claude"] = "rule"
