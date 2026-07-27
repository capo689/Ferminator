"""Explainable source-aware job freshness and Discover actionability."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class FreshnessAssessment:
    effective_at: datetime
    source: str
    confidence: str
    reason: str
    age_days: int
    tier: str
    label: str
    actionability_rank: int
    verified_refresh: bool
    default_discover_visible: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def assess_freshness(job: dict[str, Any], *, now: datetime | None = None) -> FreshnessAssessment:
    """Choose a credible effective date without treating every scan as a repost."""
    now = _aware(now) or datetime.now(UTC)
    published = _aware(job.get("published_at"))
    updated = _aware(job.get("source_updated_at"))
    first_seen = _aware(job.get("first_seen_at")) or now
    revision_count = int(job.get("revision_count") or 1)
    latest_revision_at = _aware(job.get("latest_revision_at"))
    last_seen = _aware(job.get("last_seen_at"))

    source = "first_seen"
    effective = first_seen
    confidence = "low"
    reason = "Publication date unavailable; using Ferminator's first-seen date."
    verified_refresh = False

    if published:
        effective = published
        source = "published"
        confidence = "high"
        reason = "Using the employer-provided publication date."

    if updated and (not published or updated > published):
        effective = updated
        source = "source_updated"
        confidence = "high"
        verified_refresh = True
        reason = "The ATS reports a later employer update than the publication date."

    material_revision = (
        revision_count > 1
        and latest_revision_at is not None
        and latest_revision_at > first_seen
        and latest_revision_at > effective
    )
    if material_revision:
        effective = latest_revision_at
        source = "material_revision"
        confidence = "medium"
        verified_refresh = True
        reason = "Ferminator observed a material listing revision after first discovery."

    # Ignore provider timestamps that are implausibly in the future.
    if effective > now:
        effective = first_seen
        source = "first_seen"
        confidence = "low"
        verified_refresh = False
        reason = "The provider date was implausible; using Ferminator's first-seen date."

    age_days = max(0, (now - effective).days)
    recently_revalidated = bool(last_seen and now - last_seen <= timedelta(days=3))
    if age_days <= 60:
        tier, label, rank, visible = "normal", "Active", 4, True
    elif age_days <= 90:
        tier, label, rank, visible = "older", "Older listing", 3, True
    elif age_days <= 180:
        visible = verified_refresh and recently_revalidated
        tier, label, rank = (
            "stale",
            "Older · source verified" if visible else "Needs revalidation",
            2,
        )
    elif age_days <= 365:
        visible = verified_refresh and recently_revalidated
        tier, label, rank = (
            "archived",
            "Very old · source verified" if visible else "Archived by age",
            1,
        )
    else:
        tier, label, rank, visible = "long_archived", "Archived · 1 year+", 0, False

    return FreshnessAssessment(
        effective_at=effective,
        source=source,
        confidence=confidence,
        reason=reason,
        age_days=age_days,
        tier=tier,
        label=label,
        actionability_rank=rank,
        verified_refresh=verified_refresh,
        default_discover_visible=visible,
    )


def annotate_freshness(
    matches: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    result = []
    for item in matches:
        assessment = assess_freshness(item, now=now)
        result.append(
            {
                **item,
                **{f"freshness_{key}": value for key, value in assessment.as_dict().items()},
                "freshness": (
                    f"{assessment.age_days * 24}h ago"
                    if assessment.age_days < 2
                    else f"{assessment.age_days}d ago"
                ),
            }
        )
    return result


def apply_default_freshness_policy(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve reviewed positives while archiving stale unreviewed intake."""
    return [
        item
        for item in matches
        if item.get("feedback_verdict") in {"great", "maybe"}
        or item.get("freshness_default_discover_visible", False)
    ]
