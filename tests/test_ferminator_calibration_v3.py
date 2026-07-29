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


def test_calibration_v3_loses_only_the_deliberately_excluded_positive() -> None:
    """Editorial was removed from the profile on purpose, so one labelled
    positive is now unreachable by design.

    The corpus is SHA-pinned reviewed ground truth and is deliberately left
    alone, even though Adam later rated this same job Wrong in production. The
    assertion names the one job rather than lowering a number, so any *other*
    positive going missing still fails loudly.
    """
    report = evaluate_calibration_v3(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.positives_visible == 25
    assert [d["title"] for d in report.disagreements] == ["Manager, Editorial Lead"]


def test_calibration_v3_filters_every_reviewed_wrong() -> None:
    report = evaluate_calibration_v3(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.wrong_filtered == 57
    assert report.wrong_rejection_rate == 100


def test_calibration_v3_measures_great_versus_maybe_ranking() -> None:
    report = evaluate_calibration_v3(load_profile("profiles/adam-cagle.md"), CORPUS)

    assert report.great_average_score > report.maybe_average_score
    # Dropping editorial removed a Great from the ranked pool, which costs a
    # couple of points of pairwise accuracy. Ordering still holds.
    assert report.great_maybe_pairwise_accuracy >= 68
