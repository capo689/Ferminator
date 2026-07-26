"""Structured human feedback for match calibration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

WRONG_REASON_LABELS = {
    "function_mismatch": "Not my function or kind of work",
    "too_technical": "Too technical or engineering-heavy",
    "seniority_mismatch": "Wrong seniority or level",
    "qualification_gap": "Requires experience I do not have",
    "domain_mismatch": "Wrong industry or subject-matter domain",
    "location_mismatch": "Location or workplace arrangement does not work",
    "compensation_mismatch": "Compensation does not work",
    "company_mismatch": "Not a company I want to pursue",
    "misleading_listing": "Title looked right, but the actual job is different",
    "not_interested": "Not interested after reviewing the role",
    "other": "Something else",
}

WRONG_REASON_CODES = frozenset(WRONG_REASON_LABELS)


def render_calibration_markdown(
    profile_name: str,
    records: Iterable[Mapping[str, Any]],
) -> str:
    """Render durable Wrong feedback as concise profile-calibration evidence."""
    items = list(records)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Ferminator Wrong-Match Calibration — {profile_name}",
        "",
        f"Generated: {generated}",
        f"Records: {len(items)}",
        "",
        "Use this evidence to propose profile/search-rule changes. Do not edit the",
        "career profile automatically; distinguish repeated patterns from one-off",
        "preferences and preserve the user's positive career evidence.",
        "",
    ]
    if not items:
        lines.extend(["No active Wrong feedback has been recorded.", ""])
        return "\n".join(lines)

    for index, item in enumerate(items, 1):
        code = item.get("wrong_reason_code") or "legacy_unspecified"
        label = WRONG_REASON_LABELS.get(code, "Legacy feedback without a reason")
        note = item.get("reason") or "No additional note."
        evidence = item.get("matched_evidence") or []
        concerns = item.get("concerns") or []
        description = " ".join((item.get("description_excerpt") or "").split())
        lines.extend(
            [
                f"## {index}. {item['title']} — {item['company_name']}",
                "",
                f"- Reason: **{label}** (`{code}`)",
                f"- User note: {note}",
                f"- Internal score when rated: {float(item['score_at_feedback']):.1f}",
                f"- Job URL: {item['job_url']}",
                f"- Rated: {item['updated_at'].isoformat()}",
            ]
        )
        if evidence:
            lines.append(f"- Matcher evidence: {'; '.join(evidence[:5])}")
        if concerns:
            lines.append(f"- Matcher concerns: {'; '.join(concerns[:5])}")
        if description:
            lines.extend(["", f"> JD excerpt: {description[:1600]}"])
        lines.append("")
    return "\n".join(lines)
