from pathlib import Path

from ferminator.calibration import load_calibration, summarize_calibration

CORPUS = Path("calibration/v1/corpus.jsonl")


def test_calibration_v1_is_frozen_complete_and_summarized() -> None:
    records = load_calibration(CORPUS)
    summary = summarize_calibration(records)

    assert summary.records == 58
    assert summary.known_adam_verdicts == 22
    assert summary.final_reviewer_scores == 15
    assert summary.live_verified == 18
    assert summary.recommendation_counts == {
        "pass": 10,
        "consider": 17,
        "stretch": 8,
        "apply": 23,
    }


def test_intradiem_is_an_applied_calibration_anchor() -> None:
    records = load_calibration(CORPUS)
    intradiem = next(r for r in records if r["record_id"].startswith("intradiem-"))

    assert intradiem["exact_job_title"] == "Director, Enterprise AI Enablement"
    assert intradiem["reviewer"]["overall_score"] == 82
    assert intradiem["adam"]["verdict"] == "yes_apply"
    assert intradiem["outcome"]["status"] == "applied"


def test_v1_pairwise_priority_anchors_are_preserved() -> None:
    records = {r["company"]: r for r in load_calibration(CORPUS)}

    assert records["Loka"]["outcome"]["status"] == "applied"
    assert (
        records["Evertune"]["reviewer"]["overall_score"]
        > records["Loka"]["reviewer"]["overall_score"]
    )
