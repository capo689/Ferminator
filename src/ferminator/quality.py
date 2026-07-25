"""Repeatable, profile-specific match-quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ferminator.domain import NormalizedJob
from ferminator.matching import score_job
from ferminator.profiles import CareerProfile


@dataclass(frozen=True)
class QualityReport:
    total: int
    correct: int
    false_positives: int
    false_negatives: int
    cases: tuple[dict, ...]

    @property
    def accuracy(self) -> float:
        return round(100 * self.correct / self.total, 1) if self.total else 0.0


def predicted_tier(profile: CareerProfile, job: NormalizedJob) -> tuple[str, float]:
    match = score_job(profile, job)
    if not match.eligible or match.score < profile.notifications.review_minimum_score:
        return "wrong", match.score
    if match.score >= profile.notifications.minimum_score:
        return "great", match.score
    return "maybe", match.score


def evaluate_quality(profile: CareerProfile, fixture_path: str | Path) -> QualityReport:
    payload = yaml.safe_load(Path(fixture_path).read_text())
    rows = payload.get("cases", []) if isinstance(payload, dict) else []
    cases = []
    correct = false_positives = false_negatives = 0
    for row in rows:
        expected = row["expected"]
        job = NormalizedJob.model_validate(row["job"])
        predicted, score = predicted_tier(profile, job)
        is_correct = predicted == expected
        correct += int(is_correct)
        false_positives += int(expected == "wrong" and predicted != "wrong")
        false_negatives += int(expected != "wrong" and predicted == "wrong")
        cases.append(
            {
                "name": row["name"],
                "expected": expected,
                "predicted": predicted,
                "score": score,
                "correct": is_correct,
            }
        )
    return QualityReport(
        total=len(cases),
        correct=correct,
        false_positives=false_positives,
        false_negatives=false_negatives,
        cases=tuple(cases),
    )
