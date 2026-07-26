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


def _phrase_count(text: str, phrases: tuple[str, ...]) -> int:
    """Count distinct explainable signals without rewarding keyword stuffing."""
    normalized = text.casefold()
    return sum(phrase in normalized for phrase in phrases)


def _calibration_adjustment(
    role_family: RoleFamily | None,
    title: str,
    text: str,
) -> tuple[float, list[str], list[str]]:
    """Translate broad title matches into function-aware ranking evidence.

    These signals are deliberately conservative: they change ordering and
    visibility, while hard eligibility remains in explicit profile rules.
    """
    title_text = title.casefold()
    body = text.casefold()
    adjustment = 0.0
    evidence: list[str] = []
    concerns: list[str] = []

    def add(points: float, label: str) -> None:
        nonlocal adjustment
        adjustment += points
        evidence.append(label)

    def subtract(points: float, label: str) -> None:
        nonlocal adjustment
        adjustment -= points
        concerns.append(label)

    family_id = role_family.id if role_family else ""

    if family_id in {"copywriting", "creative-direction-copy"}:
        add(15, "Direct senior copy craft")
        if (
            _phrase_count(
                body,
                (
                    "brand voice",
                    "campaign concept",
                    "conversion",
                    "landing page",
                    "lifecycle",
                    "paid media",
                    "direct response",
                    "video script",
                    "e-commerce",
                    "d2c",
                ),
            )
            >= 2
        ):
            add(5, "Commercial copy and conversion work")
        if "market access" in body or "payer" in body and "reimbursement" in body:
            subtract(24, "Specialized pharmaceutical market-access experience required")
        if (
            "legal portfolio" in body
            or "legal-content writing" in body
            or "legal content writer" in body
            or "legal content writing" in body
        ):
            subtract(18, "Specialized legal-copy portfolio required")
        if (
            _phrase_count(
                body,
                (
                    "fda",
                    "ftc",
                    "supplement",
                    "market access",
                    "medical legal review",
                    "payer",
                    "reimbursement",
                ),
            )
            >= 2
        ):
            subtract(22, "Specialized regulated-copy domain required")

    if family_id == "content-strategy-brand":
        add(12, "Direct content and brand strategy")
        if (
            _phrase_count(
                body,
                ("ai-native", "brand voice", "content system", "ai discovery", "seo", "aeo", "geo"),
            )
            >= 2
        ):
            add(8, "AI-native content-system intersection")
        if (
            _phrase_count(
                body,
                ("member support", "support content", "agent sop", "upsell", "account retention"),
            )
            >= 2
        ):
            subtract(26, "Role is primarily support or account operations")
        if "est/cst" in body or "future opening" in title_text:
            subtract(18, "Availability or working-hours constraint")

    if "developer relation" in title_text or "developer advocate" in title_text:
        subtract(14, "Formal DevRel title requires direct builder evidence")
        if "engineer" in title_text:
            subtract(14, "DevRel engineering title")
        builder_hits = _phrase_count(
            body,
            (
                "build",
                "prototype",
                "technical content",
                "documentation",
                "product feedback",
                "example application",
                "sample application",
                "make cool stuff",
                "feedback from the market",
            ),
        )
        if builder_hits >= 3:
            add(20, "Builder-oriented developer education")
        formal_hits = _phrase_count(
            body,
            (
                "developer community",
                "community growth",
                "conference",
                "event strategy",
                "public speaking",
                "established audience",
                "social following",
                "appsec",
                "devsecops",
            ),
        )
        if formal_hits >= 2:
            subtract(min(28, 7 * formal_hits), "Formal DevRel/community program ownership")

    if family_id == "creative-ai-technology":
        experiential_hits = _phrase_count(
            body,
            (
                "real-time graphics",
                "game engine",
                "unreal engine",
                "unity",
                "physical computing",
                "hardware integration",
                "av integration",
                "interactive installation",
            ),
        )
        if experiential_hits >= 2:
            subtract(42, "Experiential, real-time, or hardware creative technology")
        elif (
            _phrase_count(
                body,
                ("agent", "workflow", "api", "automation", "guardrail", "human approval"),
            )
            >= 3
        ):
            add(12, "Applied-AI creative systems")

    if family_id == "conversation-prompt-design":
        traditional_hits = _phrase_count(
            body,
            ("nlu", "tts", "voice interface", "voice assistant", "conversation design experience"),
        )
        if traditional_hits >= 2:
            subtract(22, "Traditional NLU, voice, or TTS specialization")

    if family_id == "product-marketing-narrative":
        if (
            _phrase_count(
                body,
                ("messaging", "positioning", "narrative", "product launch", "executive"),
            )
            >= 3
        ):
            add(8, "Messaging, positioning, and launch leadership")
        formal_pmm = bool(
            re.search(
                r"\b(?:4|5|6|7|8|9|10)(?:\s*[-–—]\s*(?:5|6|7|8|9|10))?\+?"
                r"\s+years?[^.]{0,90}product marketing",
                body,
            )
        )
        if formal_pmm and not re.search(
            r"product marketing[^.]{0,80}(?:related|launch management|gtm strategy)", body
        ):
            subtract(16, "Conventional product-marketing tenure gate")
        specialist_hits = _phrase_count(
            body,
            (
                "supply chain security",
                "cloud-native",
                "open source security",
                "credentials security",
                "password manager",
                "institutional trading",
                "derivatives",
                "av-over-ip",
                "dante",
                "clinical outcomes",
            ),
        )
        if specialist_hits >= 2:
            subtract(min(24, 8 * specialist_hits), "Specialized product domain required")
        if "technical product marketing" in title_text:
            subtract(14, "Formal technical product-marketing function")
        if "chainguard" in body and "product marketing" in title_text:
            subtract(10, "Cloud-native supply-chain-security PMM specialization")

    ai_builder_hits = _phrase_count(
        body,
        (
            "build ai",
            "build and deploy",
            "prototype",
            "agent",
            "api integration",
            "evaluation",
            "guardrail",
            "workflow automation",
            "python",
            "javascript",
        ),
    )
    if family_id in {
        "ai-enablement",
        "ai-transformation-operations",
        "consulting-transformation",
    }:
        if ai_builder_hits >= 3:
            add(min(16, 4 * ai_builder_hits), "Hands-on applied-AI building")
        change_hits = _phrase_count(
            body,
            (
                "training program",
                "office hours",
                "champion network",
                "change management",
                "adoption metrics",
                "guided selling",
                "sales enablement",
            ),
        )
        if (
            change_hits >= 3
            and ai_builder_hits < 3
            and family_id == "ai-enablement"
            and "director" not in title_text
        ):
            subtract(20, "Training, change, or field enablement without hands-on building")
        if "transformation owner" in title_text:
            add(8, "Cross-functional AI transformation ownership")
        if "adoption manager" in title_text and change_hits >= 3:
            subtract(22, "Formal adoption and change-management program ownership")
        if (
            "customer success" in title_text
            and _phrase_count(body, ("retention", "expansion", "renewal", "customer success")) >= 3
        ):
            subtract(24, "Enterprise Customer Success ownership")

    technical_title_hits = _phrase_count(
        title_text,
        (
            "engineering manager",
            "solutions architect",
            "technical product manager",
            "internal ai transformation",
            "product designer",
            "creative designer",
        ),
    )
    infrastructure_hits = _phrase_count(
        body,
        (
            "kubernetes",
            "mlops",
            "infrastructure as code",
            "data engineering",
            "cloud certification",
            "manage engineers",
            "incident response",
            "snowflake",
        ),
    )
    if technical_title_hits and infrastructure_hits >= 2:
        subtract(
            min(35, 15 + 5 * infrastructure_hits), "Career engineering/infrastructure ownership"
        )
    if "technical product manager" in title_text:
        subtract(24, "Formal technical-product-management tenure")
    if "ai adoption manager" in title_text:
        subtract(22, "Formal adoption and change-management program ownership")

    mandatory_degree = bool(
        re.search(
            r"(?:bachelor'?s|four-year|4-year) degree[^.]{0,45}(?:required|must)",
            body,
        )
        or re.search(
            r"(?:required|must have)[^.]{0,45}(?:bachelor'?s|four-year|4-year) degree",
            body,
        )
    )
    if mandatory_degree and "or equivalent" not in body:
        subtract(16, "Mandatory degree without equivalent-experience path")

    if "talent pool" in title_text or "future opening" in title_text:
        subtract(25, "No immediate defined opening")

    return adjustment, evidence, concerns


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

    structural_title_blocks = (
        "engineering manager",
        "product designer",
        "creative designer",
        "solutions architect",
        "engineering - internal ai",
    )
    structural_match = next(
        (phrase for phrase in structural_title_blocks if phrase in title.casefold()),
        None,
    )
    if structural_match:
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[f"Functionally excluded title: {structural_match}"],
            explanation="The title denotes a career function outside the profile evidence.",
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
                f"Location is outside the configured US search: {location_text or 'unknown'}."
            ],
            explanation="The job failed the profile geography rule.",
        )

    floor = profile.search.compensation.minimum_base_annual
    hourly_floor = profile.search.compensation.minimum_contract_hourly
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
    if (
        hourly_floor
        and comp
        and comp.interval == "hour"
        and comp.maximum is not None
        and comp.maximum < hourly_floor
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[
                f"Published hourly maximum {comp.maximum:g} is below the configured contract floor."
            ],
            explanation="The disclosed contract compensation failed a hard profile rule.",
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
    career_hits = [phrase for phrase in preferred_hits if _contains(profile.evidence_text, phrase)]
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
    adjustment, calibration_evidence, calibration_concerns = _calibration_adjustment(
        role_family,
        title,
        text,
    )
    if (
        floor
        and comp
        and comp.interval in {None, "year", "annual", "annually"}
        and comp.minimum is not None
        and comp.maximum is not None
        and comp.minimum < floor
        and comp.maximum <= floor * 1.05
    ):
        adjustment -= 18
        calibration_concerns.append(
            "Only the extreme top of the published range reaches the compensation floor"
        )
    if role_family and role_family.id == "content-strategy-brand" and comp and floor:
        if (
            comp.interval in {None, "year", "annual", "annually"}
            and comp.maximum is not None
            and comp.maximum <= floor
        ):
            adjustment -= 6
    if (
        role_family
        and role_family.id in {"copywriting", "creative-direction-copy"}
        and "per word" in title.casefold()
    ):
        adjustment -= 15
        calibration_concerns.append("Per-word engagement with undisclosed economics")
    score = round(max(0.0, min(100.0, score + adjustment)), 2)
    components["functional_calibration"] = round(adjustment, 2)
    evidence.extend(calibration_evidence)
    concerns.extend(calibration_concerns)
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
