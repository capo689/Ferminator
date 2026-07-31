"""Stage 1 and Stage 2 gates, checked against jobs we have real verdicts for.

Every case below comes from a job that actually appeared in Adam's feed on
2026-07-29 and was hand-classified, so a regression here is a regression against
observed reality rather than an invented example.
"""

from __future__ import annotations

import pytest

from ferminator.repository import SUPPRESSED_BY_HISTORY_SQL
from ferminator.search_framework import classify_remote, classify_title


def _remote(**kwargs):
    base = {
        "title": "",
        "location_labels": "",
        "description": "",
        "workplace_type": None,
        "any_location_flagged_remote": False,
    }
    base.update(kwargs)
    return classify_remote(**base)


class TestRemoteGate:
    def test_provider_marked_remote_is_remote(self) -> None:
        assert _remote(workplace_type="remote").is_remote

    def test_remote_in_the_title_counts(self) -> None:
        """Weedmaps shipped "ACD, Copy (Remote)" and the old filter hid it."""
        assert _remote(title="Associate Creative Director, Copy (Remote)").is_remote

    def test_remote_in_the_location_label_counts(self) -> None:
        assert _remote(location_labels="United States - Remote").is_remote

    def test_bare_remote_in_the_body_is_not_evidence(self) -> None:
        """JDs say "manage remote teams" constantly. That is not a remote job."""
        assert not _remote(
            description="You will manage remote teams and receive a remote work stipend."
        ).is_remote

    def test_stated_remote_in_the_body_is_evidence(self) -> None:
        assert _remote(description="This role is fully remote within the United States.").is_remote

    def test_provider_hybrid_overrides_a_remote_title(self) -> None:
        verdict = _remote(title="Brand Storyteller (Remote)", workplace_type="hybrid")
        assert not verdict.is_remote
        assert "hybrid" in verdict.reason

    def test_waymo_hybrid_schedule_overrides_everything(self) -> None:
        """Scored 100 and says so in its own body."""
        verdict = _remote(
            title="AI Enablement Lead",
            workplace_type="remote",
            description="This role follows a hybrid work schedule and reports to the manager.",
        )
        assert not verdict.is_remote
        assert "hybrid" in verdict.reason

    def test_li_hybrid_tag_overrides(self) -> None:
        """Justworks carried #LI-Hybrid with a New York range."""
        assert not _remote(workplace_type="remote", description="#LI-Hybrid #LI-CD1").is_remote

    def test_hub_radius_overrides(self) -> None:
        """Intersect: functional fit 92, unreachable from Bend."""
        verdict = _remote(
            workplace_type="remote",
            description="We are looking for candidates located within 60 miles of one of "
            "those hubs.",
        )
        assert not verdict.is_remote

    def test_mandatory_office_days_override(self) -> None:
        assert not _remote(
            workplace_type="remote",
            description="You will be in the office three days per week.",
        ).is_remote

    def test_no_evidence_is_not_remote(self) -> None:
        assert not _remote(title="Senior Copywriter", location_labels="New York, NY").is_remote


class TestTitleGate:
    @pytest.mark.parametrize(
        "title",
        [
            "AI Enablement Lead",
            "AI Transformation Owner, Marketing",
            "AI Context Operations Lead",
            "Senior Copywriter",
            "Copy Lead, Claude",
            "Applied AI Architect, GTM",
            "Senior Product Manager, Agentic AI",
        ],
    )
    def test_included_titles(self, title: str) -> None:
        assert classify_title(title).included, title

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Editor in Chief, SEO & AEO Content", "editorial"),
            ("Social Media Manager", "social / community / creator"),
            ("Staff FinOps AI Governance Lead", "engineering / data / infrastructure"),
            ("Lead GTM Data Operations Analyst, AI Workflows",
             "engineering / data / infrastructure"),
            ("Manager, Campaign Operations", "revenue / marketing operations"),
            ("Content Marketing Manager", "generic content role"),
            ("Creative Director", "generic creative leadership"),
        ],
    )
    def test_excluded_titles(self, title: str, expected: str) -> None:
        verdict = classify_title(title)
        assert not verdict.included, title
        assert verdict.excluded_by == expected

    def test_marketing_ai_operations_is_excluded_despite_the_interior_modifier(self) -> None:
        """The trap: this does not contain the literal "Marketing Operations".

        A substring exclusion list admits the exact Airtable role the framework
        is written to reject, because "AI" sits between the two words.
        """
        verdict = classify_title("Senior Manager, Marketing AI Operations")
        assert not verdict.included
        assert verdict.excluded_by == "revenue / marketing operations"

    def test_exclusion_beats_inclusion(self) -> None:
        """"AI Operations" is a primary title; the role is still data operations."""
        assert not classify_title("AI Operations Data Engineer").included

    def test_copy_rescues_generic_creative_leadership(self) -> None:
        assert classify_title("Associate Creative Director, Copy").included

    def test_seo_rescues_a_generic_content_title(self) -> None:
        assert classify_title("Content Manager, SEO").included


def test_history_suppression_has_exactly_one_definition() -> None:
    """Guard against a second copy drifting out of sync.

    An ad-hoc export bypassed this predicate and shipped four already-applied
    roles. Any query that shows jobs to a user has to use this constant.
    """
    assert "job_history" in SUPPRESSED_BY_HISTORY_SQL
    assert "h.permanent or h.suppress_until > now()" in SUPPRESSED_BY_HISTORY_SQL
    assert "normalize_job_part" in SUPPRESSED_BY_HISTORY_SQL


class TestForeignRemoteGate:
    def test_remote_uk_label_is_not_us_remote(self) -> None:
        """"Remote-UK&I" reached review on the strength of the word remote."""
        verdict = _remote(location_labels="Remote-UK&I")
        assert not verdict.is_remote
        assert "restricted" in verdict.reason

    @pytest.mark.parametrize("label", ["Remote - EMEA", "Canada - Remote", "Remote (Europe)"])
    def test_foreign_region_labels_fail(self, label: str) -> None:
        assert not _remote(location_labels=label).is_remote

    @pytest.mark.parametrize(
        "label",
        ["Remote - US or Canada", "Remote, North America", "United States - Remote", "Remote"],
    )
    def test_us_or_unscoped_labels_pass(self, label: str) -> None:
        assert _remote(location_labels=label).is_remote
