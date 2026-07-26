from ferminator.calibration_v2 import (
    evaluate_calibration_v2,
    load_calibration_v2,
)
from ferminator.profiles import load_profile

CORPUS = "calibration/v2/corpus.jsonl"


def test_calibration_v2_is_frozen_and_complete() -> None:
    records = load_calibration_v2(CORPUS)

    assert len(records) == 61
    assert {
        classification: sum(r["human"]["classification"] == classification for r in records)
        for classification in ("great", "maybe", "wrong", "duplicate")
    } == {"great": 11, "maybe": 8, "wrong": 40, "duplicate": 2}


def test_calibration_v2_preserves_every_reviewed_positive() -> None:
    report = evaluate_calibration_v2(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.positives_visible == 19
    assert report.positive_recall == 100


def test_calibration_v2_filters_most_reviewed_wrongs_without_killing_recall() -> None:
    report = evaluate_calibration_v2(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.wrong_filtered >= 34
    assert report.wrong_rejection_rate >= 85
