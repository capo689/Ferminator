"""Shared user-visible Discover filtering.

Keep production audits and the web page on the same filtering path so upstream
match counts cannot be mistaken for opportunities a user can actually see.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ferminator.geography import is_remote_job, job_distance_miles, lookup_zip
from ferminator.matching import matched_role_family
from ferminator.profiles import CareerProfile

_RELEVANCE_VERDICT_PRIORITY = {
    "great": 3,
    None: 2,
    "maybe": 1,
    "wrong": 0,
    "duplicate": 0,
}


def sort_discover_matches(matches: list[dict], sort: str) -> list[dict]:
    """Order Discover results without letting machine scores overrule reviews."""

    def date_value(item: dict) -> datetime:
        return item.get("published_at") or item.get("first_seen_at") or datetime.min.replace(
            tzinfo=UTC
        )

    if sort == "newest":
        return sorted(
            matches,
            key=lambda item: (date_value(item), item["score"]),
            reverse=True,
        )

    return sorted(
        matches,
        key=lambda item: (
            _RELEVANCE_VERDICT_PRIORITY.get(item.get("feedback_verdict"), 2),
            item.get("display_score", item["score"]),
            item["score"],
            date_value(item),
        ),
        reverse=True,
    )


def apply_role_thresholds(
    profile: CareerProfile,
    matches: list[dict],
    overrides: dict[str, int],
) -> list[dict]:
    """Annotate and filter matches using each role family's visibility floor."""
    result = []
    for item in matches:
        family = matched_role_family(
            profile,
            item["title"],
            item.get("compensation_text") or item.get("description_text") or "",
        )
        if family is None:
            continue
        threshold = overrides.get(family.id, family.threshold)
        if item["score"] < threshold:
            continue
        result.append(
            {
                **item,
                "role_family_id": family.id,
                "role_family": family.label,
                "role_threshold": threshold,
            }
        )
    return result


def apply_default_discover_filters(
    profile: CareerProfile,
    matches: list[dict],
) -> list[dict]:
    """Apply the feedback and default geography rules used by `/discover`."""
    visible = [
        item
        for item in matches
        if item.get("feedback_verdict") not in {"wrong", "duplicate"}
    ]
    rules = profile.search
    if rules.default_location_mode == "anywhere":
        return visible
    origin = lookup_zip(rules.default_zip)
    result = []
    for item in visible:
        distance = job_distance_miles(item, origin) if origin else None
        remote = is_remote_job(item)
        near = distance is not None and distance <= rules.default_radius_miles
        if (
            rules.default_location_mode == "remote"
            and remote
            or rules.default_location_mode == "near"
            and near
            or rules.default_location_mode == "remote_or_near"
            and (remote or near)
        ):
            result.append(item)
    return result
