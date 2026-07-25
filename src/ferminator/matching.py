"""Explainable deterministic job matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ferminator.domain import NormalizedJob, WorkplaceType
from ferminator.profiles import CareerProfile


def _contains(text: str, phrase: str) -> bool:
    return phrase.casefold() in text.casefold()


def _matched(text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if _contains(text, phrase)]


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
    blocked = _matched(text, excluded_phrases) + _matched(title, excluded_titles)
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

    floor = profile.search.compensation.minimum_base_annual
    comp = job.compensation
    if floor and comp and comp.maximum is not None and comp.maximum < floor:
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

    high = _matched(title, profile.high_titles)
    adjacent = _matched(title, profile.adjacent_titles)
    if high:
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

    preferred_hits = _matched(text, profile.search.preferred)
    # A richer profile vocabulary must not lower a job's score. Four independent
    # preferred signals are enough to earn the full skills component.
    preferred_factor = min(1.0, len(preferred_hits) / 4)
    components["skills"] = weights.get("skills", 0) * preferred_factor
    evidence.extend(f"Preferred evidence: {item}" for item in preferred_hits)

    evidence_terms = [
        line[2:].strip()
        for line in profile.markdown_body.splitlines()
        if line.startswith("- ") and "TODO:" not in line
    ]
    career_hits = _matched(text, evidence_terms)
    evidence_factor = min(1.0, len(career_hits) / max(1, min(4, len(evidence_terms))))
    components["career_evidence"] = weights.get("career_evidence", 0) * evidence_factor
    evidence.extend(f"Career evidence: {item}" for item in career_hits[:5])

    seniority_hits = _matched(title, profile.search.target_seniority)
    components["seniority"] = weights.get("seniority", 0) * (1.0 if seniority_hits else 0.25)
    evidence.extend(f"Seniority: {item}" for item in seniority_hits)

    location_text = " ".join(location.label for location in job.locations)
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
