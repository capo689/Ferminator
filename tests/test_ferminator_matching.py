from datetime import UTC, datetime
from pathlib import Path

from ferminator.domain import (
    ATSProvider,
    Compensation,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
)
from ferminator.matching import matched_role_family, score_job
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
        "locations": [JobLocation(label="Remote — United States", is_primary=True, is_remote=True)],
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


def test_ai_labeled_software_engineering_role_is_ineligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    result = score_job(profile, make_job(title="Senior Software Engineer, AI Transformation"))

    assert not result.eligible
    assert result.score == 0
    assert "Software Engineer" in result.concerns[0]


def test_ai_enablement_engineering_false_positive_is_ineligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    result = score_job(profile, make_job(title="Sr. AI Enablement Engineer"))

    assert not result.eligible
    assert result.score == 0
    assert "AI Enablement Engineer" in result.concerns[0]


def test_reordered_excluded_engineering_title_is_ineligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    result = score_job(profile, make_job(title="Engineer, Applied AI"))

    assert not result.eligible
    assert "Applied AI Engineer" in result.concerns[0]


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


def test_provider_fulltime_variants_match_profile_employment_type():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    for employment_type in (
        "FullTime",
        "Permanent Full Time Employee",
        "Full-time Remote",
        "full-time",
    ):
        result = score_job(profile, make_job(employment_type=employment_type))
        assert result.eligible, employment_type


def test_profile_backed_technical_evidence_earns_career_credit():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    job = make_job(
        title="Senior Manager, Marketing AI Operations",
        description_text=(
            "Build governed marketing systems using AI agents, RAG, APIs, and human approval."
        ),
    )

    result = score_job(profile, job)

    assert result.eligible
    assert result.score >= profile.notifications.minimum_score
    assert result.component_scores["career_evidence"] >= 15
    assert "Career evidence: AI agents" in result.matched_evidence


def test_advertising_copywriter_is_a_primary_eligible_role():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    job = make_job(
        title="Senior Advertising Copywriter",
        description_text=(
            "Lead brand voice, executive communication, content systems, "
            "and creative technology for integrated campaigns."
        ),
    )

    result = score_job(profile, job)
    family = matched_role_family(profile, job.title)

    assert result.eligible
    assert family is not None
    assert family.id == "copywriting"
    assert family.threshold == 50
    assert "Role family: Copywriting" in result.matched_evidence


def test_product_marketing_is_kept_in_the_controlled_review_tier():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    family = matched_role_family(profile, "Director of Product Marketing")

    assert family is not None
    assert family.id == "product-marketing-narrative"
    assert family.tier == "edge"
    assert family.threshold == 60
