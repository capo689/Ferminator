from ferminator.calibration_v3 import evaluate_calibration_v3, load_calibration_v3
from ferminator.profiles import load_profile

CORPUS = "calibration/v3/corpus.jsonl"


def test_calibration_v3_is_frozen_and_complete() -> None:
    records = load_calibration_v3(CORPUS)

    assert len(records) == 85
    assert {
        classification: sum(r["human"]["classification"] == classification for r in records)
        for classification in ("great", "maybe", "wrong", "duplicate")
    } == {"great": 13, "maybe": 13, "wrong": 57, "duplicate": 2}


def test_calibration_v3_preserves_every_reviewed_positive() -> None:
    report = evaluate_calibration_v3(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.positives_visible == 26
    assert report.positive_recall == 100


def test_calibration_v3_filters_every_reviewed_wrong() -> None:
    report = evaluate_calibration_v3(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.wrong_filtered == 57
    assert report.wrong_rejection_rate == 100
