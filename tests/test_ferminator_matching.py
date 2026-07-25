from datetime import UTC, datetime
from pathlib import Path

from ferminator.domain import (
    ATSProvider,
    Compensation,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
)
from ferminator.matching import score_job
from ferminator.profiles import load_profile


def make_job(**overrides):
    values = {
        "provider": ATSProvider.GREENHOUSE,
        "board_key": "example",
        "source_job_id": "1",
        "company_slug": "example-company",
        "company_name": "Example Company",
        "title": "Director, AI Enablement",
        "description_text": (
            "Lead enterprise AI adoption, cross-functional operations, "
            "technical writing, executive communication, and enablement programs."
        ),
        "workplace_type": WorkplaceType.REMOTE,
        "locations": [
            JobLocation(label="Remote — United States", is_primary=True, is_remote=True)
        ],
        "compensation": Compensation(
            minimum=190000,
            maximum=230000,
            currency="USD",
            interval="year",
        ),
        "job_url": "https://example.com/jobs/1",
        "published_at": datetime.now(UTC),
    }
    values.update(overrides)
    return NormalizedJob(**values)


def test_strong_job_is_eligible_and_explainable():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    result = score_job(profile, make_job())

    assert result.eligible
    assert result.score >= profile.notifications.minimum_score
    assert result.component_scores["role_alignment"] == 30
    assert "Target title: AI Enablement" in result.matched_evidence
    assert result.explanation.startswith("Score")


def test_excluded_title_is_ineligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    result = score_job(profile, make_job(title="Enterprise Account Executive"))

    assert not result.eligible
    assert result.score == 0
    assert "Account Executive" in result.concerns[0]


def test_description_only_keyword_overlap_is_ineligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    job = make_job(
        title="PR Director, APAC",
        description_text="Executive communication, AI adoption, and enablement programs.",
        locations=[JobLocation(label="Singapore", is_primary=True, is_remote=True)],
    )

    result = score_job(profile, job)

    assert not result.eligible
    assert result.score == 0


def test_foreign_remote_role_is_ineligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    job = make_job(
        title="Director, AI Enablement",
        locations=[JobLocation(label="India - Remote", is_primary=True, is_remote=True)],
    )

    result = score_job(profile, job)

    assert not result.eligible
    assert "outside the configured US search" in result.concerns[0]


def test_us_remote_role_remains_eligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(profile, make_job())

    assert result.eligible


def test_profile_backed_technical_evidence_earns_career_credit():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    job = make_job(
        title="Senior Manager, Marketing AI Operations",
        description_text=(
            "Build governed marketing systems using AI agents, RAG, APIs, "
            "and human approval."
        ),
    )

    result = score_job(profile, job)

    assert result.eligible
    assert result.score >= profile.notifications.minimum_score
    assert result.component_scores["career_evidence"] >= 15
    assert "Career evidence: AI agents" in result.matched_evidence
