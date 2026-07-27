from datetime import UTC, datetime, timedelta

from ferminator.freshness import (
    annotate_freshness,
    apply_default_freshness_policy,
    assess_freshness,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _job(**overrides):
    return {
        "published_at": NOW - timedelta(days=10),
        "source_updated_at": None,
        "first_seen_at": NOW - timedelta(days=9),
        "last_seen_at": NOW,
        "revision_count": 1,
        "latest_revision_at": NOW - timedelta(days=9),
        "feedback_verdict": None,
        **overrides,
    }


def test_source_update_can_make_an_old_publication_actionable() -> None:
    result = assess_freshness(
        _job(
            published_at=NOW - timedelta(days=200),
            source_updated_at=NOW - timedelta(days=12),
        ),
        now=NOW,
    )

    assert result.source == "source_updated"
    assert result.verified_refresh
    assert result.tier == "normal"
    assert result.default_discover_visible


def test_last_seen_never_refreshes_an_old_listing() -> None:
    result = assess_freshness(
        _job(
            published_at=NOW - timedelta(days=120),
            first_seen_at=NOW - timedelta(days=2),
            last_seen_at=NOW,
        ),
        now=NOW,
    )

    assert result.age_days == 120
    assert result.tier == "stale"
    assert not result.default_discover_visible


def test_unknown_publication_uses_first_seen_with_low_confidence() -> None:
    result = assess_freshness(
        _job(published_at=None, first_seen_at=NOW - timedelta(days=4)),
        now=NOW,
    )

    assert result.source == "first_seen"
    assert result.confidence == "low"
    assert result.age_days == 4


def test_reviewed_positives_survive_default_archiving() -> None:
    rows = annotate_freshness(
        [
            _job(id="unreviewed", published_at=NOW - timedelta(days=400)),
            _job(
                id="great",
                published_at=NOW - timedelta(days=400),
                feedback_verdict="great",
            ),
            _job(
                id="maybe",
                published_at=NOW - timedelta(days=220),
                feedback_verdict="maybe",
            ),
        ],
        now=NOW,
    )

    assert [item["id"] for item in apply_default_freshness_policy(rows)] == [
        "great",
        "maybe",
    ]


def test_verified_very_old_listing_can_remain_visible_until_one_year() -> None:
    rows = annotate_freshness(
        [
            _job(
                id="verified",
                published_at=NOW - timedelta(days=340),
                source_updated_at=NOW - timedelta(days=250),
                last_seen_at=NOW,
            ),
            _job(
                id="unverified",
                published_at=NOW - timedelta(days=250),
                source_updated_at=None,
                last_seen_at=NOW,
            ),
        ],
        now=NOW,
    )

    assert [item["id"] for item in apply_default_freshness_policy(rows)] == ["verified"]


def test_freshness_tiers_follow_60_90_180_365_policy() -> None:
    assert assess_freshness(_job(published_at=NOW - timedelta(days=60)), now=NOW).tier == "normal"
    assert assess_freshness(_job(published_at=NOW - timedelta(days=61)), now=NOW).tier == "older"
    assert assess_freshness(_job(published_at=NOW - timedelta(days=91)), now=NOW).tier == "stale"
    assert assess_freshness(_job(published_at=NOW - timedelta(days=181)), now=NOW).tier == "archived"
    assert (
        assess_freshness(_job(published_at=NOW - timedelta(days=366)), now=NOW).tier
        == "long_archived"
    )
