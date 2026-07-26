from datetime import UTC, datetime

from ferminator.feedback import render_calibration_markdown


def test_calibration_markdown_contains_reason_evidence_and_job_context() -> None:
    content = render_calibration_markdown(
        "Adam Cagle",
        [
            {
                "title": "AI Software Engineer",
                "company_name": "Example",
                "job_url": "https://example.com/job",
                "wrong_reason_code": "too_technical",
                "reason": "This role writes production code.",
                "score_at_feedback": 71,
                "matched_evidence": ["AI enablement"],
                "concerns": ["Python required"],
                "description_excerpt": "Build and operate production ML systems.",
                "updated_at": datetime(2026, 7, 26, tzinfo=UTC),
            }
        ],
    )

    assert "Too technical or engineering-heavy" in content
    assert "This role writes production code." in content
    assert "AI enablement" in content
    assert "Python required" in content
    assert "Build and operate production ML systems." in content
