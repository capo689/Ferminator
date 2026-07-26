"""Explainable deterministic job matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ferminator.domain import NormalizedJob, WorkplaceType
from ferminator.profiles import CareerProfile, RoleFamily

_US_LOCATION_MARKERS = (
    "united states",
    "u.s.",
    "u.s. remote",
    "us remote",
    "remote - us",
    "remote — us",
    "remote, us",
    "namER",
)
_FOREIGN_LOCATION_MARKERS = (
    "apac",
    "emea",
    "india",
    "japan",
    "singapore",
    "korea",
    "dubai",
    "uae",
    "ireland",
    "dublin",
    "london",
    "berlin",
    "paris",
    "brussels",
    "united kingdom",
    "uk",
    "toronto",
    "montreal",
    "canada",
)


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold() in text.casefold()


def _matched(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if _contains(text, phrase)]


def matched_role_family(profile: CareerProfile, title: str) -> RoleFamily | None:
    """Return the most specific configured family represented in a job title."""
    tier_priority = {"primary": 2, "adjacent": 1, "edge": 0}
    candidates = [
        (max(len(alias) for alias in family.aliases if _contains(title, alias)), family)
        for family in profile.role_families
        if any(_contains(title, alias) for alias in family.aliases)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], tier_priority[item[1].tier]))[1]


def _employment_matches(value: str, accepted: list[str]) -> bool:
    """Normalize common ATS spelling and punctuation variants."""
    compact_value = re.sub(r"[^a-z0-9]", "", value.casefold())
    aliases = {
        "permanentfulltimeemployee": "fulltime",
        "permanentfulltime": "fulltime",
        "regularfulltime": "fulltime",
        "fulltimeemployee": "fulltime",
        "fulltimeremote": "fulltime",
        "temporarycontract": "contract",
        "contractor": "contract",
    }
    compact_value = aliases.get(compact_value, compact_value)
    accepted_values = {
        aliases.get(compact, compact)
        for item in accepted
        if (compact := re.sub(r"[^a-z0-9]", "", item.casefold()))
    }
    return compact_value in accepted_values


def _matched_title_exclusions(title: str, phrases: list[str]) -> list[str]:
    """Catch punctuation and provider word-order variants in excluded titles."""
    title_tokens = set(re.findall(r"[a-z0-9]+", title.casefold()))
    matches = []
    for phrase in phrases:
        phrase_tokens = set(re.findall(r"[a-z0-9]+", phrase.casefold()))
        if _contains(title, phrase) or (len(phrase_tokens) >= 2 and phrase_tokens <= title_tokens):
            matches.append(phrase)
    return matches


def _is_us_compatible_location(job: NormalizedJob, location_text: str) -> bool:
    """Accept explicit US roles and reject clearly foreign-only remote listings."""
    country_codes = {
        (location.country_code or "").strip().upper()
        for location in job.locations
        if location.country_code
    }
    if "US" in country_codes:
        return True
    normalized = location_text.casefold()
    if any(marker.casefold() in normalized for marker in _US_LOCATION_MARKERS):
        return True
    if any(marker.casefold() in normalized for marker in _FOREIGN_LOCATION_MARKERS):
        return False
    # A provider that says only "Remote" has not contradicted the US default.
    return bool(
        job.workplace_type == WorkplaceType.REMOTE
        and (not normalized.strip() or normalized.strip() == "remote")
    )


@dataclass(frozen=True)
class MatchResult:
    eligible: bool
    score: float
    component_scores: dict[str, float] = field(default_factory=dict)
    matched_evidence: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    explanation: str = ""


def score_job(profile: CareerProfile, job: NormalizedJob) -> MatchResult:
    """Apply hard eligibility followed by transparent weighted ranking."""
    text = job.search_document
    title = job.title
    concerns: list[str] = []

    excluded_phrases = profile.search.exclude.get("phrases", [])
    excluded_titles = profile.search.exclude.get("title_phrases", [])
    blocked = _matched(text, excluded_phrases) + _matched_title_exclusions(
        title,
        excluded_titles,
    )
    if blocked:
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[f"Excluded phrase: {phrase}" for phrase in blocked],
            explanation="The job failed a profile exclusion rule.",
        )

    required = profile.search.required_any
    if required and not _matched(text, required):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["None of the required concepts appeared."],
            explanation="The job did not satisfy any required concept.",
        )

    if (
        job.employment_type
        and profile.search.employment_types
        and not _employment_matches(job.employment_type, profile.search.employment_types)
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[f"Employment type is {job.employment_type}."],
            explanation="The job failed the profile employment-type rule.",
        )

    high = _matched(title, profile.high_titles)
    adjacent = _matched(title, profile.adjacent_titles)
    role_family = matched_role_family(profile, title)
    if profile.search.require_title_match and not (high or adjacent):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["No target or adjacent concept appeared in the title."],
            explanation="Description-only keyword overlap is not sufficient for eligibility.",
        )

    preferred_hits = _matched(text, profile.search.preferred)
    if (
        adjacent
        and not high
        and len(preferred_hits) < profile.search.adjacent_minimum_preferred_hits
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["The adjacent title lacked supporting profile evidence."],
            explanation="A broad adjacent title needs evidence in the job description.",
        )

    location_text = " ".join(location.label for location in job.locations)
    if (
        profile.search.enforce_default_geography
        and any("united states" in item.casefold() for item in profile.search.default_geography)
        and not _is_us_compatible_location(job, location_text)
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[
                f"Location is outside the configured US search: "
                f"{location_text or 'unknown'}."
            ],
            explanation="The job failed the profile geography rule.",
        )

    floor = profile.search.compensation.minimum_base_annual
    comp = job.compensation
    if (
        floor
        and comp
        and comp.interval in {None, "year", "annual", "annually"}
        and comp.maximum is not None
        and comp.maximum < floor
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[f"Published maximum {comp.maximum:g} is below the configured floor."],
            explanation="The disclosed compensation failed a hard profile rule.",
        )
    if floor and comp is None and not profile.search.allow_jobs_without_compensation:
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["Compensation is not disclosed."],
            explanation="The profile requires disclosed compensation.",
        )

    weights = profile.scoring
    components: dict[str, float] = {}
    evidence: list[str] = []

    if role_family:
        role_factor = {"primary": 1.0, "adjacent": 0.82, "edge": 0.72}[role_family.tier]
        evidence.append(f"Role family: {role_family.label}")
        evidence.extend(f"Target title: {item}" for item in high)
        evidence.extend(f"Adjacent title: {item}" for item in adjacent)
    elif high:
        role_factor = 1.0
        evidence.extend(f"Target title: {item}" for item in high)
    elif adjacent:
        role_factor = 0.72
        evidence.extend(f"Adjacent title: {item}" for item in adjacent)
    else:
        body_hits = _matched(text, profile.high_titles + profile.adjacent_titles)
        role_factor = min(0.55, 0.18 * len(body_hits))
        evidence.extend(f"Role concept: {item}" for item in body_hits)
    components["role_alignment"] = weights.get("role_alignment", 0) * role_factor

    # A richer profile vocabulary must not lower a job's score. Four independent
    # preferred signals are enough to earn the full skills component.
    preferred_factor = min(1.0, len(preferred_hits) / 4)
    components["skills"] = weights.get("skills", 0) * preferred_factor
    evidence.extend(f"Preferred evidence: {item}" for item in preferred_hits)

    # Preferred concepts only earn career-evidence credit when the profile's
    # factual narrative also contains them. Matching full resume bullets
    # verbatim made this component effectively unreachable.
    career_hits = [
        phrase
        for phrase in preferred_hits
        if _contains(profile.evidence_text, phrase)
    ]
    evidence_factor = min(1.0, len(career_hits) / 4)
    components["career_evidence"] = weights.get("career_evidence", 0) * evidence_factor
    evidence.extend(f"Career evidence: {item}" for item in career_hits[:5])

    seniority_hits = _matched(title, profile.search.target_seniority)
    components["seniority"] = weights.get("seniority", 0) * (1.0 if seniority_hits else 0.25)
    evidence.extend(f"Seniority: {item}" for item in seniority_hits)

    remote_ok = job.workplace_type == WorkplaceType.REMOTE or _contains(location_text, "remote")
    geography_hits = _matched(location_text, profile.search.default_geography)
    geography_factor = 1.0 if remote_ok or geography_hits else 0.2
    components["geography"] = weights.get("geography", 0) * geography_factor
    if remote_ok:
        evidence.append("Remote-compatible")
    elif not geography_hits:
        concerns.append("Location does not clearly match the profile default.")

    if comp and comp.minimum is not None:
        compensation_factor = 1.0 if not floor or comp.minimum >= floor else 0.5
        evidence.append("Published compensation available")
    else:
        compensation_factor = 0.0
        concerns.append("Compensation is not disclosed.")
    components["compensation"] = weights.get("compensation", 0) * compensation_factor

    components["company_preference"] = 0.0

    if job.published_at:
        age_days = max(0, (datetime.now(UTC) - job.published_at).days)
        freshness_factor = max(0.0, 1 - age_days / 30)
    else:
        age_days = None
        freshness_factor = 0.35
    components["freshness"] = weights.get("freshness", 0) * freshness_factor
    if age_days is not None and age_days <= 1:
        evidence.append("Newly published")

    score = round(min(100.0, sum(components.values())), 2)
    # Adjacent titles have already passed the explicit supporting-evidence gate.
    # Keep them visible in the controlled review tier without promoting them to
    # the strong-match tier solely through a floor.
    if adjacent and not high:
        score = max(score, profile.notifications.review_minimum_score)
    strongest = ", ".join(item for item in evidence[:3]) or "limited direct evidence"
    explanation = f"Score {score:g}: strongest signals are {strongest}."
    return MatchResult(
        eligible=True,
        score=score,
        component_scores={key: round(value, 2) for key, value in components.items()},
        matched_evidence=evidence,
        concerns=concerns,
        explanation=explanation,
    )
