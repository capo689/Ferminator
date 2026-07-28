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
    assert result.explanation.startswith("Gateway 5")


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
    assert result.explanation.startswith("Gateway 1")


def test_geography_precedes_other_rejection_work():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="Senior Software Engineer, AI Transformation",
            locations=[JobLocation(label="India - Remote", is_primary=True, is_remote=True)],
        ),
    )

    assert result.explanation.startswith("Gateway 1")


def test_unconventional_title_can_advance_from_jd_function_evidence():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="Strategic Programs Lead",
            description_text=(
                "Own AI adoption and AI enablement programs using AI agents, "
                "workflow automation, guardrails, and human approval."
            ),
        ),
    )

    assert result.eligible
    assert "Role family inferred from JD evidence" in result.matched_evidence
    assert result.score <= 59
    assert any("Controlled review" in concern for concern in result.concerns)


def test_jd_ai_vocabulary_does_not_rescue_unrelated_legal_title():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="Director, Privacy Counsel",
            description_text=(
                "Advise teams using AI adoption, workflow automation, AI governance, "
                "APIs, guardrails, and human approval."
            ),
        ),
    )

    assert not result.eligible
    assert result.explanation.startswith("Gateway 3")
    assert "Counsel" in result.concerns[0]


def test_jd_content_vocabulary_does_not_rescue_unrelated_engineering_program_title():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="Sr. Principal Program Manager, ASIC Post-Silicon Engineering",
            description_text=(
                "Own content strategy, brand voice, executive communication, "
                "workflow design, and cross-functional operations."
            ),
        ),
    )

    assert not result.eligible
    assert result.explanation.startswith("Gateway 3")


def test_direct_ai_phrase_does_not_rescue_incompatible_title_function():
    profile = load_profile(Path("profiles/adam-cagle.md"))

    for title in (
        "Strategic Finance, AI Innovation",
        "Enterprise Data Architect & AI Solutions Leader",
        "Senior Applied Researcher AI/ML",
    ):
        result = score_job(profile, make_job(title=title))
        assert not result.eligible, title
        assert result.explanation.startswith("Gateway 3")


def test_jd_keywords_do_not_rescue_body_only_engineering_title():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="Staff Engineer, Developer Experience",
            description_text=(
                "Own AI adoption and AI enablement programs using AI agents, "
                "workflow automation, guardrails, and human approval."
            ),
        ),
    )

    assert not result.eligible
    assert result.explanation.startswith("Gateway 3")


def test_hard_disqualifier_precedes_compensation():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="Senior Software Engineer, AI Transformation",
            compensation=Compensation(
                minimum=40000,
                maximum=50000,
                currency="USD",
                interval="year",
            ),
        ),
    )

    assert result.explanation.startswith("Gateway 3")


def test_explicit_low_compensation_is_gateway_four():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            compensation=Compensation(
                minimum=40000,
                maximum=50000,
                currency="USD",
                interval="year",
            )
        ),
    )

    assert result.explanation.startswith("Gateway 4")


def test_gateway_four_extracts_compensation_from_stored_jd():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            compensation=None,
            description_text=(
                "Lead enterprise AI adoption and workflow automation. "
                "The salary range for this role is $60,000—$80,000 per year."
            ),
        ),
    )

    assert not result.eligible
    assert result.explanation.startswith("Gateway 4")


def test_mandatory_residency_timezone_rejects_an_incompatible_remote_role():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="AI Success Manager, Central",
            description_text=(
                "Lead AI adoption and workflow automation. This role is remote, "
                "but candidates must be located in the US Central timezone."
            ),
        ),
    )

    assert not result.eligible
    assert result.explanation.startswith("Gateway 3")
    assert "Central" in result.concerns[0]
    assert "Pacific" in result.concerns[0]


def test_timezone_overlap_request_does_not_become_a_residency_rejection():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="AI Success Manager",
            description_text=(
                "Lead AI adoption and workflow automation. Collaborate with customers "
                "during Central time-zone business hours when needed."
            ),
        ),
    )

    assert result.eligible


def test_explicit_travel_above_profile_maximum_is_a_hard_disqualifier():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            title="AI Engagement Manager",
            description_text=(
                "Lead enterprise AI adoption and workflow automation. Travel could "
                "reach 50% at peak for on-site customer engagements."
            ),
        ),
    )

    assert not result.eligible
    assert result.explanation.startswith("Gateway 3")
    assert "50% travel" in result.concerns[0]


def test_travel_at_profile_maximum_remains_eligible():
    profile = load_profile(Path("profiles/adam-cagle.md"))
    result = score_job(
        profile,
        make_job(
            description_text=(
                "Lead enterprise AI adoption and workflow automation. "
                "The role requires up to 25% travel."
            ),
        ),
    )

    assert result.eligible


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


def _adam():
    return load_profile(Path("profiles/adam-cagle.md"))


def test_remote_usa_label_is_not_treated_as_foreign():
    """Regression, from the live corpus: Zillow "Senior AI Program Manager, Talent".

    workplace_type was already `remote` and the label read "Remote-USA", yet the
    geography gate rejected it with score 0. The old fallback demanded the label
    be exactly "remote", so every provider that decorated the word at all was
    read as foreign.
    """
    job = make_job(
        title="Senior AI Program Manager",
        workplace_type=WorkplaceType.REMOTE,
        locations=[JobLocation(label="Remote-USA", is_primary=True, is_remote=True)],
    )

    result = score_job(_adam(), job)

    assert result.eligible, result.concerns


def test_city_state_labels_resolve_as_united_states():
    """country_code is null on every board for the five largest providers, so a
    "Boston, MA" style label was the only evidence available and was read as
    foreign. Postal geography knows better than a marker list."""
    for label in ("Boston, MA", "Boise, ID - Main Site", "New York, New York", "Austin, TX"):
        job = make_job(
            workplace_type=WorkplaceType.ON_SITE,
            locations=[JobLocation(label=label, is_primary=True)],
        )
        result = score_job(_adam(), job)
        assert "outside the configured US search" not in " ".join(result.concerns), label


def test_us_and_foreign_city_together_keeps_the_us_option():
    job = make_job(
        workplace_type=WorkplaceType.ON_SITE,
        locations=[JobLocation(label="San Francisco, CA | London", is_primary=True)],
    )

    result = score_job(_adam(), job)

    assert "outside the configured US search" not in " ".join(result.concerns)


def test_same_city_name_abroad_is_still_rejected():
    """Vancouver WA is in the US; Vancouver BC is not. A marker list cannot tell
    them apart, which is why the postal dataset does the work."""
    near = score_job(
        _adam(),
        make_job(
            workplace_type=WorkplaceType.ON_SITE,
            locations=[JobLocation(label="Vancouver, WA", is_primary=True)],
        ),
    )
    abroad = score_job(
        _adam(),
        make_job(
            workplace_type=WorkplaceType.ON_SITE,
            locations=[JobLocation(label="Vancouver, British Columbia, Canada", is_primary=True)],
        ),
    )

    assert "outside the configured US search" not in " ".join(near.concerns)
    assert not abroad.eligible
    assert "outside the configured US search" in " ".join(abroad.concerns)


def test_foreign_remote_role_is_still_rejected():
    """The recall work must not open the gate to remote-in-another-country."""
    for label in ("Remote - Canada", "Portugal Remote", "EMEA", "Remote - South East Asia"):
        job = make_job(
            workplace_type=WorkplaceType.REMOTE,
            locations=[JobLocation(label=label, is_primary=True, is_remote=True)],
        )
        result = score_job(_adam(), job)
        assert not result.eligible, f"{label} should not be eligible"


def test_unparseable_placeholder_defers_to_the_posting():
    """Workday collapses locations to "3 Locations" and stores nothing else, so
    the label carries no signal. Unparseable is not evidence of foreign, but it
    is not evidence of US either: the posting has to say so."""
    silent = make_job(
        workplace_type=WorkplaceType.ON_SITE,
        locations=[JobLocation(label="3 Locations", is_primary=True)],
        description_text="Lead enterprise AI adoption and enablement programs.",
    )
    speaks_up = make_job(
        workplace_type=WorkplaceType.ON_SITE,
        locations=[JobLocation(label="3 Locations", is_primary=True)],
        description_text=(
            "Lead enterprise AI adoption and enablement programs. "
            "This role is remote within the United States."
        ),
    )

    assert not score_job(_adam(), silent).eligible
    assert "outside the configured US search" not in " ".join(
        score_job(_adam(), speaks_up).concerns
    )


def test_recurring_onsite_requirement_is_rejected():
    """Regression: these reached the feed on the strength of a "…, United
    States" label and had to be rejected by hand. Adam cannot make a weekly
    commute to New York."""
    cases = (
        "This is a hybrid role that has in-office requirements of two (2) days per week.",
        "ID.me is a full-time, in-office culture.",
        "We ask that you work from the office at least three days a week.",
    )
    for sentence in cases:
        job = make_job(
            workplace_type=WorkplaceType.ON_SITE,
            locations=[JobLocation(label="New York, New York, United States", is_primary=True)],
            description_text="Own AI enablement programs. " + sentence,
        )
        result = score_job(_adam(), job)
        assert not result.eligible, sentence
        assert "on-site presence" in " ".join(result.concerns)


def test_onsite_language_does_not_reject_a_remote_job():
    """Plenty of remote postings mention offices in passing."""
    job = make_job(
        workplace_type=WorkplaceType.REMOTE,
        locations=[JobLocation(label="Remote — United States", is_primary=True, is_remote=True)],
        description_text=(
            "Own AI enablement programs. Teams gather in the office two days per week "
            "when they choose to, but this role is fully remote."
        ),
    )

    assert score_job(_adam(), job).eligible


def test_onsite_requirement_within_commute_is_kept():
    """An on-site role Adam can actually drive to stays eligible."""
    job = make_job(
        workplace_type=WorkplaceType.ON_SITE,
        locations=[JobLocation(label="Bend, OR", is_primary=True)],
        description_text=(
            "Own AI enablement programs. This is a hybrid role with in-office "
            "requirements of two (2) days per week."
        ),
    )

    result = score_job(_adam(), job)

    assert "on-site presence" not in " ".join(result.concerns)
