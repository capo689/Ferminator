from datetime import UTC, datetime, timedelta
from pathlib import Path

from ferminator.discover_visibility import (
    apply_default_discover_filters,
    apply_role_thresholds,
    sort_discover_matches,
)
from ferminator.profiles import load_profile


def _job(
    title: str,
    *,
    score: float = 70,
    verdict: str | None = None,
    remote: bool = True,
) -> dict:
    return {
        "id": title,
        "title": title,
        "score": score,
        "feedback_verdict": verdict,
        "workplace": "remote" if remote else "on-site",
        "location": "Remote - US" if remote else "New York, NY",
        "locations": [
            {
                "label": "Remote - US" if remote else "New York, NY",
                "is_remote": remote,
            }
        ],
    }


def test_default_discover_accounting_uses_all_user_visible_filters():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    candidates = [
        _job("Senior Copywriter", score=72),
        _job("Content Marketing Manager", score=65),
        _job("Senior Copywriter", score=49),
        _job("Senior Copywriter", verdict="wrong"),
        _job("Senior Copywriter", verdict="duplicate"),
        _job("Senior Copywriter", remote=False),
        _job("Software Engineer, AI Content", score=95),
    ]

    thresholded = apply_role_thresholds(profile, candidates, {})
    visible = apply_default_discover_filters(profile, thresholded)

    assert [item["id"] for item in visible] == [
        "Senior Copywriter",
        "Content Marketing Manager",
    ]


def test_role_override_is_part_of_the_audited_path():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    candidate = _job("Senior Copywriter", score=64)

    assert apply_role_thresholds(profile, [candidate], {})
    assert not apply_role_thresholds(profile, [candidate], {"copywriting": 65})


def test_relevance_sort_puts_human_greats_before_unrated_before_maybes():
    now = datetime.now(UTC)
    matches = [
        {
            **_job("High-scoring Maybe", score=95, verdict="maybe"),
            "display_score": 96,
            "published_at": now,
        },
        {
            **_job("Lower-scoring Great", score=55, verdict="great"),
            "display_score": 72,
            "published_at": now - timedelta(days=3),
        },
        {
            **_job("Best unrated", score=90),
            "display_score": 95,
            "published_at": now - timedelta(days=2),
        },
        {
            **_job("Second unrated", score=70),
            "display_score": 87,
            "published_at": now - timedelta(days=1),
        },
    ]

    ranked = sort_discover_matches(matches, "relevance")

    assert [item["title"] for item in ranked] == [
        "Lower-scoring Great",
        "Best unrated",
        "Second unrated",
        "High-scoring Maybe",
    ]


def test_relevance_sort_keeps_rejected_at_the_bottom_when_explicitly_shown():
    now = datetime.now(UTC)
    matches = [
        {
            **_job("Duplicate", score=99, verdict="duplicate"),
            "display_score": 96,
            "published_at": now,
        },
        {
            **_job("Wrong", score=98, verdict="wrong"),
            "display_score": 96,
            "published_at": now,
        },
        {
            **_job("Unrated", score=60),
            "display_score": 78,
            "published_at": now,
        },
    ]

    ranked = sort_discover_matches(matches, "relevance")

    assert [item["title"] for item in ranked] == ["Unrated", "Duplicate", "Wrong"]


def test_newest_sort_remains_a_true_date_sort():
    now = datetime.now(UTC)
    matches = [
        {
            **_job("Older Great", score=80, verdict="great"),
            "display_score": 93,
            "published_at": now - timedelta(days=2),
        },
        {
            **_job("New Maybe", score=60, verdict="maybe"),
            "display_score": 78,
            "published_at": now,
        },
    ]

    ranked = sort_discover_matches(matches, "newest")

    assert [item["title"] for item in ranked] == ["New Maybe", "Older Great"]
