"""Consumer-facing calibration for Ferminator's conservative relevance score."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchDisplay:
    score: int
    label: str
    band: str


_ANCHORS = (
    (0.0, 35.0),
    (52.0, 68.0),
    (60.0, 78.0),
    (68.0, 85.0),
    (75.0, 91.0),
    (100.0, 96.0),
)


def calibrate_display_score(raw_score: float) -> int:
    """Translate raw relevance without changing its ordering."""
    raw = max(0.0, min(100.0, float(raw_score)))
    for (raw_low, shown_low), (raw_high, shown_high) in zip(_ANCHORS, _ANCHORS[1:]):
        if raw <= raw_high:
            position = (raw - raw_low) / (raw_high - raw_low)
            return round(shown_low + position * (shown_high - shown_low))
    return 96


def match_display(raw_score: float) -> MatchDisplay:
    score = calibrate_display_score(raw_score)
    if score >= 90:
        return MatchDisplay(score, "Exceptional", "exceptional")
    if score >= 85:
        return MatchDisplay(score, "Excellent", "excellent")
    if score >= 78:
        return MatchDisplay(score, "Strong", "strong")
    if score >= 68:
        return MatchDisplay(score, "Possible", "possible")
    return MatchDisplay(score, "Exploratory", "exploratory")
