from pathlib import Path

from ferminator.discover_visibility import (
    apply_default_discover_filters,
    apply_role_thresholds,
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
