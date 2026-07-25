from pathlib import Path

import pytest
from pydantic import ValidationError

from ferminator.profiles import load_profile


def test_adam_profile_is_valid():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    assert profile.profile.slug == "adam-cagle"
    assert profile.search.scan_interval_hours == 12
    assert sum(profile.scoring.values()) == 100
    assert "AI Enablement" in profile.high_titles
    assert "AI Transformation" in profile.high_titles
    assert "Customer Education" in profile.adjacent_titles
    assert profile.notifications.review_minimum_score == 58


def test_profile_requires_weights_to_total_100(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text(
        """---
schema_version: 1
profile:
  slug: bad-profile
  display_name: Bad
search: {}
scoring:
  role_alignment: 20
---
# Evidence
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="must total 100"):
        load_profile(path)


def test_profile_requires_front_matter(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text("# No front matter", encoding="utf-8")

    with pytest.raises(ValueError, match="missing YAML"):
        load_profile(path)
