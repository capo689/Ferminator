"""Explainable deterministic job matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ferminator.domain import NormalizedJob, WorkplaceType, extract_compensation_from_text
from ferminator.geography import coordinates_for_label, distance_miles, lookup_zip
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


def matched_role_family(
    profile: CareerProfile,
    title: str,
    evidence_text: str = "",
) -> RoleFamily | None:
    """Return the strongest family from the title, falling back to JD evidence."""
    tier_priority = {"primary": 2, "adjacent": 1, "edge": 0}
    title_candidates = [
        (max(len(alias) for alias in family.aliases if _contains(title, alias)), family)
        for family in profile.role_families
        if any(_contains(title, alias) for alias in family.aliases)
    ]
    if title_candidates:
        return max(
            title_candidates,
            key=lambda item: (item[0], tier_priority[item[1].tier]),
        )[1]
    if not evidence_text:
        return None
    body_candidates = [
        (
            sum(_contains(evidence_text, alias) for alias in family.aliases),
            max(len(alias) for alias in family.aliases if _contains(evidence_text, alias)),
            family,
        )
        for family in profile.role_families
        if any(_contains(evidence_text, alias) for alias in family.aliases)
    ]
    if not body_candidates:
        return None
    return max(
        body_candidates,
        key=lambda item: (item[0], item[1], tier_priority[item[2].tier]),
    )[2]


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


def _body_inference_matches_title(role_family: RoleFamily, title: str) -> bool:
    """Require a plausible title function before JD evidence assigns a family.

    Descriptions routinely mention AI, content, enablement, and operations in
    roles whose actual function is finance, law, engineering, events, or data.
    The body may clarify an unconventional title, but it may not replace the
    title's career function entirely.
    """
    anchors = {
        "ai-enablement": (
            r"\b(?:enablement|adoption|education|learning|training|evangelist|"
            r"community|change|programs?|outcomes?|success)\b"
        ),
        "ai-transformation-operations": (
            r"\b(?:ai|automation|transformation|innovation|workflow|"
            r"implementation|deployment|context operations|marketing ai)\b"
        ),
        "ai-content-systems": (
            r"\b(?:content|editorial|knowledge|brand voice|conversation)\b"
        ),
        "creative-ai-technology": (
            r"\b(?:creative|ai|agentic|automation|technolog(?:y|ist)|"
            r"marketing engineer)\b"
        ),
        "copywriting": r"\b(?:copy|copywriter|copywriting)\b",
        "creative-direction-copy": r"\b(?:copy|creative)\b",
        "content-strategy-brand": (
            r"\b(?:content|brand|editorial|communications?|copy|messaging|"
            r"narrative|storytelling|creative)\b"
        ),
        "technical-content-education": (
            r"\b(?:technical (?:content|writ)|developer (?:relations|advocacy|"
            r"education)|documentation|docs|education|learning|training|"
            r"evangelist|content)\b"
        ),
        "ai-search": r"\b(?:ai search|aeo|geo|seo|search|discoverability)\b",
        "conversation-prompt-design": r"\b(?:conversation|conversational|prompt)\b",
        "content-creative-operations": (
            r"\b(?:content|creative|editorial|knowledge|campaign|"
            r"marketing operations)\b"
        ),
        "consulting-transformation": (
            r"\b(?:consultant|consulting|transformation|implementation|solutions)\b"
        ),
        "product-marketing-narrative": (
            r"\b(?:product marketing|growth marketing|integrated marketing|"
            r"positioning|narrative)\b"
        ),
        "agency-creative-leadership": (
            r"\b(?:creative|copy|campaign|brand)\b"
        ),
    }
    pattern = anchors.get(role_family.id)
    return bool(pattern and re.search(pattern, title, re.I))


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
                "cardiometabolic",
                "health product",
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
        people_domain_hits = _phrase_count(
            body,
            (
                "recruiting",
                "talent",
                "people operations",
                "people team",
                "human resources",
                "applicant tracking",
                "candidate communication",
                "offer-to-hire",
            ),
        )
        if people_domain_hits >= 4:
            subtract(40, "Recruiting, People, or HR operating experience required")
        enterprise_outcomes_hits = _phrase_count(
            body,
            (
                "fortune 500",
                "multi-quarter",
                "organizational change",
                "executive sponsor",
                "operating model",
                "transformation roadmap",
                "strategic account",
                "portfolio of customers",
            ),
        )
        if (
            "strategic ai outcomes manager" in title_text
            and enterprise_outcomes_hits >= 3
        ):
            subtract(34, "Formal enterprise transformation and account ownership")
        if (
            "ai engagement manager" in title_text
            and _phrase_count(
                body,
                (
                    "technical program management",
                    "software development lifecycle",
                    "sdlc",
                    "resource utilization",
                    "engagement cost",
                    "50% travel",
                    "50 percent travel",
                ),
            )
            >= 3
        ):
            subtract(28, "Enterprise technical-program and engagement ownership")

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


def desirability_prior(role_family: RoleFamily | None) -> float:
    """Great-vs-Maybe ranking prior learned from Calibration V3.

    Keep this out of eligibility: retrieval recall and Wrong rejection must not
    change merely because a role family tends to convert from Maybe to Great.
    """
    if role_family is None:
        return 0
    return {
        "copywriting": 6,
        "creative-direction-copy": 5,
        "content-strategy-brand": 4,
        "technical-content-education": 3,
        "product-marketing-narrative": -5,
        "consulting-transformation": -3,
    }.get(role_family.id, 0)


_PLACEHOLDER_LOCATION = re.compile(
    r"^\s*(?:\d+\s+locations?|all locations?|multiple locations?|various|unspecified)\s*\.?\s*$",
    re.I,
)
_EXPLICIT_US = re.compile(r"\b(?:usa|u\.s\.a\.?|united states|nationwide)\b|^\s*u\.?s\.?\s*$", re.I)
_US_STATE_NAMES = re.compile(
    r"\b(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida"
    r"|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland"
    r"|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada"
    r"|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma"
    r"|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah"
    r"|vermont|virginia|washington|west virginia|wisconsin|wyoming"
    r"|district of columbia|puerto rico)\b",
    re.I,
)
# Words that describe how you work rather than where. What remains after these
# are stripped is the label's actual claim about place.
_REMOTE_WORDS = re.compile(
    r"\b(?:remote|remotely|hybrid|anywhere|flexible|work from home|wfh|distributed|virtual)\b"
    r"|[^\w\s]", re.I,
)
_REMOTE_IN_US = re.compile(
    r"remote[^.\n]{0,40}\b(?:usa|u\.s\.|united states)\b"
    r"|\b(?:usa|u\.s\.|united states)\b[^.\n]{0,40}remote",
    re.I,
)


def _names_a_us_place(location_text: str) -> bool:
    """True when any piece of the label resolves against the US postal dataset.

    The dataset is the authority on what is a US place, which beats a marker
    list: it knows Vancouver WA is in the US and Vancouver BC is not, and it
    covers every "Boise, ID" style label no hand-written list would.
    """
    for piece in re.split(r"[;|]|\s{2,}", location_text):
        piece = piece.strip()
        if piece and coordinates_for_label(piece) is not None:
            return True
    return False


def _is_us_compatible_location(job: NormalizedJob, location_text: str) -> bool:
    """Accept explicit US roles and reject clearly foreign-only remote listings.

    Providers almost never populate country_code (it is null for every board on
    Workday, Greenhouse, Ashby, SmartRecruiters and Lever), so this falls
    through to the label on essentially every job. A short marker list was the
    only thing left holding the gate, which meant "Remote-USA" and "Boston, MA"
    were both read as foreign while "New York, NY, United States" sailed
    through. Resolve the label against real postal geography instead.
    """
    country_codes = {
        (location.country_code or "").strip().upper()
        for location in job.locations
        if location.country_code
    }
    if "US" in country_codes:
        return True
    normalized = location_text.casefold()

    # A US signal wins over a foreign one. "San Francisco, CA | London" offers a
    # US option, so the job is reachable even though a foreign city is listed.
    if (
        any(marker.casefold() in normalized for marker in _US_LOCATION_MARKERS)
        or _EXPLICIT_US.search(location_text)
        or _US_STATE_NAMES.search(location_text)
        or _names_a_us_place(location_text)
    ):
        return True
    if any(marker.casefold() in normalized for marker in _FOREIGN_LOCATION_MARKERS):
        return False

    # Nothing identifiable in the label. Being unparseable is not evidence of
    # being foreign, but it is not evidence of the US either.
    if _PLACEHOLDER_LOCATION.match(location_text.strip()) or not normalized.strip():
        # The provider gave us nothing, so workplace_type is unreliable too.
        # Only the posting's own words can settle it.
        return bool(_REMOTE_IN_US.search(job.search_document))
    # A label naming somewhere unrecognised is naming somewhere. "Portugal
    # Remote" is remote, but not remote here, and the foreign marker list is
    # far too short to be trusted as the only guard. Accept a remote job only
    # when the label claims no place at all.
    if job.workplace_type == WorkplaceType.REMOTE:
        return not _REMOTE_WORDS.sub(" ", location_text).strip()
    return False


_ONSITE_CADENCE = (
    # "in-office requirements of two (2) days per week"
    r"in[- ]?office requirements?[^.\n]{0,40}days?",
    # "three days per week in the office", "2 days/week onsite"
    r"\b(?:one|two|three|four|five|[1-5])\s*(?:\(\d\)\s*)?days?\s*(?:per|a|each|/)\s*week"
    r"[^.\n]{0,50}(?:(?:in|at|from)[- ]?(?:the\s+)?office|on[-\s]?site|in[- ]?person|hub|hq)",
    # "work from the office at least three days a week"
    r"(?:(?:in|at|from)[- ]?(?:the\s+)?office|on[-\s]?site|in[- ]?person)[^.\n]{0,50}"
    r"\b(?:one|two|three|four|five|[1-5])\s*(?:\(\d\)\s*)?days?\s*(?:per|a|each|/)\s*week",
    # "full-time, in-office culture", "100% onsite"
    r"full[- ]?time,?\s+in[- ]?office",
    r"\b100\s*%\s*(?:in[- ]?office|on[-\s]?site)",
    r"\bthis (?:is|role is) a hybrid (?:role|position)\b",
)


def _requires_onsite_presence(text: str) -> str | None:
    """Return the phrase showing the job demands recurring physical presence."""
    for pattern in _ONSITE_CADENCE:
        match = re.search(pattern, text, re.I)
        if match:
            return " ".join(match.group(0).split())[:120]
    return None


def _is_within_commute(profile: CareerProfile, job: NormalizedJob) -> bool:
    """True when any of the job's locations sits inside the profile's radius."""
    origin = lookup_zip(profile.search.default_zip)
    if origin is None:
        return False
    for location in job.locations:
        place = coordinates_for_label(location.label)
        if place and distance_miles(origin, place) <= profile.search.default_radius_miles:
            return True
    return False


def _required_residency_timezone(text: str) -> str | None:
    """Return an explicit US residency timezone, ignoring mere overlap requests."""
    patterns = (
        r"(?:must|required to)\s+(?:be\s+)?(?:located|reside|live)"
        r"[^.\n]{0,80}\b(pacific|mountain|central|eastern)\b"
        r"(?:\s+(?:time\s*)?zone)?",
        r"(?:located|reside|live)\s+in[^.\n]{0,60}\b"
        r"(pacific|mountain|central|eastern)\b\s+(?:time\s*)?zone",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).casefold()
    return None


def _maximum_required_travel(text: str) -> int | None:
    """Find explicit travel percentages without treating benefit copy as travel."""
    percentages = []
    patterns = (
        r"(?:travel|on-site|onsite)[^.\n]{0,55}?(?:~|up to|reach|about)?\s*"
        r"(\d{1,3})\s*(?:%|percent)",
        r"(\d{1,3})\s*(?:%|percent)[^.\n]{0,30}(?:travel|on-site|onsite)",
    )
    for pattern in patterns:
        percentages.extend(int(value) for value in re.findall(pattern, text, re.I))
    return max(percentages) if percentages else None


@dataclass(frozen=True)
class MatchResult:
    eligible: bool
    score: float
    component_scores: dict[str, float] = field(default_factory=dict)
    matched_evidence: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    explanation: str = ""


def score_job(profile: CareerProfile, job: NormalizedJob) -> MatchResult:
    """Apply largest-safe-cut gateways followed by transparent fit ranking."""
    text = job.search_document
    title = job.title
    concerns: list[str] = []

    # Gateway 1: geography is the largest safe cut for a location-bound search.
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
            explanation="Gateway 1 — geography rejected this job.",
        )

    # Gateway 1b: recurring physical presence. Being in the US is not enough
    # when the posting demands two days a week in a building the candidate
    # cannot reach. These used to pass on the strength of a "…, United States"
    # label and then had to be rejected by hand, one at a time.
    if profile.search.default_location_mode in {"remote", "remote_or_near"}:
        onsite = _requires_onsite_presence(text)
        if (
            onsite
            and job.workplace_type != WorkplaceType.REMOTE
            and not _contains(location_text, "remote")
            and not _is_within_commute(profile, job)
        ):
            return MatchResult(
                eligible=False,
                score=0,
                concerns=[f"Requires recurring on-site presence away from home: {onsite}."],
                explanation="Gateway 1 — on-site requirement rejected this job.",
            )

    # Gateway 2: broad functional recall. A title signal is strongest; an
    # unconventional title may advance when its JD contains both a configured
    # role family and at least one major profile concept.
    high = _matched(title, profile.high_titles)
    adjacent = _matched(title, profile.adjacent_titles)
    title_role_family = matched_role_family(profile, title)
    preferred_hits = _matched(text, profile.search.preferred)
    role_family = title_role_family or matched_role_family(profile, title, text)
    body_function_signal = bool(role_family and preferred_hits)
    if profile.search.require_title_match and not (high or adjacent or body_function_signal):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["No supported title or JD function signal appeared."],
            explanation="Gateway 2 — functional relevance rejected this job.",
        )

    # Gateway 3: decisive function and eligibility negatives.
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
            explanation="Gateway 3 — a hard disqualifier rejected this job.",
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
            explanation="Gateway 3 — the title is outside the supported career function.",
        )

    if re.fullmatch(r"(?:senior\s+)?creative director", title.strip(), re.I):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["Generic visual Creative Director role lacks a copy-led title."],
            explanation="Gateway 3 — generic visual creative direction is outside the profile.",
        )

    incompatible_title_function = re.search(
        r"\b(?:strategic finance|finance manager|counsel|attorney|"
        r"data architect|solutions architect|applied researcher|research scientist|"
        r"asic|post-silicon|field cto|data governance|"
        r"event manager|assessment content|marketing operations)\b",
        title,
        re.I,
    )
    if incompatible_title_function:
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[
                f"Functionally excluded title: {incompatible_title_function.group(0)}"
            ],
            explanation="Gateway 3 — the title is outside the supported career function.",
        )

    required_timezone = _required_residency_timezone(job.description_text)
    if (
        required_timezone
        and profile.search.home_timezone
        and required_timezone != profile.search.home_timezone
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[
                f"Role requires {required_timezone.title()} time-zone residency; "
                f"profile is {profile.search.home_timezone.title()}."
            ],
            explanation="Gateway 3 — a mandatory residency timezone rejected this job.",
        )

    required_travel = _maximum_required_travel(job.description_text)
    if (
        required_travel is not None
        and profile.search.maximum_travel_percent is not None
        and required_travel > profile.search.maximum_travel_percent
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=[
                f"Role requires up to {required_travel}% travel; profile maximum is "
                f"{profile.search.maximum_travel_percent}%."
            ],
            explanation="Gateway 3 — explicit travel exceeds the configured maximum.",
        )

    if title_role_family is None:
        body_only_technical = re.search(
            r"\b(?:engineer|architect|developer|scientist|analytics?|"
            r"infrastructure|grc|information technology|it engineer|"
            r"technical program manager|systems? (?:manager|architect)|"
            r"product manager|product owner|incident|finance|fellows?|"
            r"architecture|system integrator)\b",
            title,
            re.I,
        )
        if body_only_technical:
            return MatchResult(
                eligible=False,
                score=0,
                concerns=[
                    "JD keywords cannot override an unsupported technical or specialist title."
                ],
                explanation="Gateway 3 — body-only evidence conflicted with the title function.",
            )
        if role_family is None or not _body_inference_matches_title(role_family, title):
            return MatchResult(
                eligible=False,
                score=0,
                concerns=[
                    "The JD signal did not agree with the career function named in the title."
                ],
                explanation=(
                    "Gateway 3 — body-only evidence lacked functionally coherent "
                    "title support."
                ),
            )

    required = profile.search.required_any
    if required and not _matched(text, required):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["None of the required concepts appeared."],
            explanation="Gateway 3 — the job missed a required profile concept.",
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
            explanation="Gateway 3 — employment type rejected this job.",
        )

    if (
        adjacent
        and not high
        and len(preferred_hits) < profile.search.adjacent_minimum_preferred_hits
    ):
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["The adjacent title lacked supporting profile evidence."],
            explanation="Gateway 3 — an adjacent title lacked supporting JD evidence.",
        )

    # Gateway 4: only explicit incompatible compensation rejects. Missing pay
    # advances with uncertainty and is handled in the refined score.
    floor = profile.search.compensation.minimum_base_annual
    hourly_floor = profile.search.compensation.minimum_contract_hourly
    comp = job.compensation or extract_compensation_from_text(job.description_text)
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
            explanation="Gateway 4 — disclosed compensation is below the annual floor.",
        )
    if floor and comp is None and not profile.search.allow_jobs_without_compensation:
        return MatchResult(
            eligible=False,
            score=0,
            concerns=["Compensation is not disclosed."],
            explanation="Gateway 4 — the profile requires disclosed compensation.",
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
            explanation="Gateway 4 — disclosed compensation is below the contract floor.",
        )

    weights = profile.runtime_scoring
    components: dict[str, float] = {}
    evidence: list[str] = []

    if role_family:
        role_factor = (
            {"primary": 1.0, "adjacent": 0.82, "edge": 0.72}[role_family.tier]
            if title_role_family
            else {"primary": 0.48, "adjacent": 0.42, "edge": 0.36}[role_family.tier]
        )
        evidence.append(f"Role family: {role_family.label}")
        if not title_role_family:
            evidence.append("Role family inferred from JD evidence")
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
    if title_role_family is None and score > 59:
        score = 59.0
        calibration_concerns.append(
            "Controlled review: role family is inferred from JD rather than title"
        )
    components["functional_calibration"] = round(adjustment, 2)
    components["desirability_prior"] = desirability_prior(role_family)
    evidence.extend(calibration_evidence)
    concerns.extend(calibration_concerns)
    strongest = ", ".join(item for item in evidence[:3]) or "limited direct evidence"
    explanation = f"Gateway 5 — refined fit score {score:g}: strongest signals are {strongest}."
    return MatchResult(
        eligible=True,
        score=score,
        component_scores={key: round(value, 2) for key, value in components.items()},
        matched_evidence=evidence,
        concerns=concerns,
        explanation=explanation,
    )
