from ferminator.profiles import load_profile
from ferminator.quality import evaluate_quality


def test_adam_golden_set_has_no_false_positive_regressions() -> None:
    report = evaluate_quality(
        load_profile("profiles/adam-cagle.md"),
        "tests/golden/adam-match-quality.yaml",
    )

    assert report.total >= 8
    assert report.false_positives == 0
    assert report.accuracy >= 80
