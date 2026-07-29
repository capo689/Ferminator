"""Stage 1 and Stage 2 of the job-hunt funnel.

Implements Adam's high-yield search framework: a remote-only gate, then title
inclusion and exclusion. Deliberately deterministic and cheap. Nothing here
reads for fit; that is Stage 5's job.

Rule precedence, from the framework:

    exclusion beats inclusion, and the description beats the title.

A title saying "remote" means nothing if the body says three days in the office.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Stage 1: remote
# --------------------------------------------------------------------------

# Positive remote evidence. The framework only ever listed location
# *exclusions*, so this is the missing half, written to be specific rather than
# generous: bare "remote" anywhere in a body is not evidence, because JDs say
# "manage remote teams" and "remote work stipend" constantly.
_REMOTE_BODY = re.compile(
    r"(?:fully|100%|entirely|permanently)[\s-]remote"
    r"|remote[\s-]first"
    r"|work from anywhere"
    r"|remote (?:within|in|across) the (?:us|u\.s\.|united states)"
    r"|(?:this|the) (?:role|position|job) is (?:fully )?remote"
    r"|open to remote"
    r"|remote \(us\)|remote[,\s]+us(?:a)?\b",
    re.I,
)

# Label or title mentions are weaker but count, because providers put the real
# answer there constantly ("United States - Remote", "ACD, Copy (Remote)").
_REMOTE_LABEL = re.compile(r"\bremote\b", re.I)

# On-site evidence strong enough to override a remote claim. Ordered by how
# unambiguous they are.
_ONSITE = [
    (re.compile(r"#LI-Hybrid", re.I), "tagged #LI-Hybrid"),
    (re.compile(r"\bhybrid\s+(?:role|position|schedule|work|model)\b", re.I), "hybrid role"),
    (re.compile(r"follows a hybrid work schedule", re.I), "hybrid schedule stated"),
    (
        re.compile(r"\b(?:two|three|four|2|3|4|5)\+?\s*days?\s*(?:per|a)\s*week\s*"
                   r"(?:in|at)\s*(?:the\s*)?office", re.I),
        "mandatory office days",
    ),
    (
        re.compile(r"\b(?:in|at)\s*(?:the\s*)?office\s*"
                   r"(?:two|three|four|2|3|4|5)\+?\s*days?", re.I),
        "mandatory office days",
    ),
    (
        re.compile(r"must (?:be able to )?(?:reside|live|be located|be based)\s*"
                   r"(?:with)?in\s*(?:\d+\s*miles|commuting)", re.I),
        "residence radius required",
    ),
    (
        re.compile(r"within\s*\d+\s*miles\s*of\s*(?:one of\s*)?(?:those|our|the)?\s*"
                   r"(?:hub|office|location)", re.I),
        "hub radius required",
    ),
    (re.compile(r"relocation (?:is )?required", re.I), "relocation required"),
    (re.compile(r"\bon-?site\s+(?:role|position)\b", re.I), "on-site role"),
]


@dataclass(frozen=True)
class RemoteVerdict:
    is_remote: bool
    reason: str


def classify_remote(
    *,
    title: str,
    location_labels: str,
    description: str,
    workplace_type: str | None,
    any_location_flagged_remote: bool,
) -> RemoteVerdict:
    """Decide whether a job is genuinely remote.

    Evidence is taken from the provider field, the title, the location labels
    and the body, in that order of trust. On-site evidence in the body then
    overrides any of it, because the description beats the title.
    """
    positives: list[str] = []
    if (workplace_type or "").casefold() == "remote":
        positives.append("provider marked it remote")
    if any_location_flagged_remote:
        positives.append("location flagged remote")
    if _REMOTE_LABEL.search(title):
        positives.append("remote in the title")
    if _REMOTE_LABEL.search(location_labels):
        positives.append("remote in the location")
    if _REMOTE_BODY.search(description):
        positives.append("remote stated in the description")

    if not positives:
        return RemoteVerdict(False, "no remote evidence")

    # A provider that positively marked the job hybrid or on-site settles it,
    # which is the rule that stopped a hybrid San Francisco job reaching a
    # completed application.
    if (workplace_type or "").casefold() in {"hybrid", "on-site", "onsite"}:
        return RemoteVerdict(False, f"provider marked it {workplace_type}")

    for pattern, label in _ONSITE:
        if pattern.search(description):
            return RemoteVerdict(False, f"{label} in the description")

    return RemoteVerdict(True, "; ".join(positives))


# --------------------------------------------------------------------------
# Stage 2: titles
# --------------------------------------------------------------------------

PRIMARY_AI_TITLES = [
    "AI Enablement", "AI Adoption", "AI Transformation", "AI Operations",
    "AI Deployment", "AI Engagement", "Applied AI", "AI Solutions", "AI Success",
    "AI Implementation", "AI Workflow", "AI Automation", "AI Systems",
    "Agent Architect", "Agentic AI", "Agentic Product", "AI Product Manager",
    "AI Product Owner", "AI Product Lead", "Forward Deployed Product",
    "AI Strategy and Operations", "AI Context Operations",
    "AI Knowledge Architecture", "Prompt Engineer", "Prompt Architect",
    "AI Builder", "AI Solutions Engineer", "AI Enablement Engineer",
    "AI Adoption Engineer", "AI Deployment Strategist", "AI Deployment Manager",
    "AI Engagement Lead", "AI Enablement Specialist", "AI Enablement Lead",
    "AI Enablement Manager", "AI Enablement Director", "AI Transformation Owner",
    "AI Creative Engineer", "Creative Technologist",
]

PRIMARY_COPY_TITLES = [
    "Copywriter", "Senior Copywriter", "Lead Copywriter", "Copy Lead",
    "Brand Copywriter", "Creative Copywriter", "Product Copywriter",
    "Technical Copywriter", "AI Copywriter", "Copy Director", "Head of Copy",
    "Brand Voice Lead",
]

CONDITIONAL_COPY_LEADERSHIP = [
    "Associate Creative Director, Copy", "Associate Creative Director, Copywriter",
    "ACD, Copy", "Creative Director, Copy",
]

SEARCH_AND_WEB_TITLES = [
    "SEO Strategist", "SEO Lead", "SEO Manager", "AEO Strategist",
    "GEO Strategist", "SEO/AEO", "SEO/GEO", "Organic Search", "AI Search",
    "Search Innovation", "Growth Workflow Specialist", "Web Strategy",
    "Website Experience", "Digital Experience", "Web Product Manager",
]

CONDITIONAL_TITLES = [
    "AI Solutions Architect", "Solutions Engineer", "Marketing AI Operations",
    "AI Program Manager", "Technical Program Manager", "Developer Advocate",
    "AI Consultant", "AI Strategist", "Content Strategist", "Technical Writer",
    "Technical Content Writer", "Content Technical Writer", "Product Manager",
    "Customer Success Manager", "Sales Enablement Manager",
]

# Title exclusions. Each entry is a regex rather than a literal because
# substring matching is not enough: "Marketing AI Operations" does not contain
# "Marketing Operations", so a literal list silently admits the exact Airtable
# role the framework means to reject. Interior modifiers have to be allowed for.
_EXCLUSIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(editorial|editor|managing editor|editor.in.chief|newsroom"
                r"|journalis\w*|publisher|publication manager)\b", re.I), "editorial"),
    (re.compile(r"\bsocial media (manager|director|strategist)\b"
                r"|\bhead of social\b|\bsocial lead\b|\bsocial content manager\b"
                r"|\bcommunity (manager|lead)\b|\bcreator (partnerships|manager)\b"
                r"|\binfluencer\b|\baudience development\b|\bchannel manager\b", re.I),
     "social / community / creator"),
    (re.compile(r"\b(machine learning|ml|ai/ml)\s+engineer\b|\bresearch scientist\b"
                r"|\bapplied scientist\b|\bdata scientist\b|\bdata engineer\b"
                r"|\banalytics engineer\b|\bbusiness intelligence\b"
                r"|\bdata\s+\w*\s*operations\b|\bsoftware engineer\b|\bdevops\b"
                r"|\bmlops\b|\bfinops\b|\bcloud architect\b|\benterprise architect\b"
                r"|\binfrastructure architect\b|\bsecurity engineer\b"
                r"|\bquantitative\b", re.I), "engineering / data / infrastructure"),
    # "Marketing AI Operations" and "GTM Data Operations" both have to land here.
    (re.compile(r"\brevenue operations\b|\brevops\b"
                r"|\bmarketing(\s+\w+)?\s+operations\b"
                r"|\bcampaign operations\b|\bsales operations\b"
                r"|\bgtm(\s+\w+)?\s+operations\b|\bcrm admin\w*\b"
                r"|\bsalesforce admin\w*\b|\bmarketo admin\w*\b"
                r"|\bpipeline operations\b", re.I), "revenue / marketing operations"),
    (re.compile(r"\binstructional designer\b|\blearning and development\b"
                r"|\btalent (enablement|development)\b|\bcurriculum\b"
                r"|\btraining manager\b|\borganizational development\b"
                r"|\bpeople operations\b|\bhr transformation\b", re.I),
     "learning / HR / org development"),
]

# Generic creative leadership is rejected unless the title names Copy, AI, or
# Creative Technology. Adam is a creative director; he is not looking to be one.
_GENERIC_CREATIVE = re.compile(
    r"\b(executive |group |associate )?(creative director|design director"
    r"|art director|vp,? creative|head of creative)\b", re.I
)
_CREATIVE_RESCUE = re.compile(r"\bcopy\w*\b|\bai\b|\bcreative technolog", re.I)

# Generic content roles are rejected unless the title names an accepted
# specialism.
_GENERIC_CONTENT = re.compile(
    r"\bcontent (marketing manager|manager|director|lead|operations|producer)\b"
    r"|\bhead of content\b", re.I
)
_CONTENT_RESCUE = re.compile(
    r"\bcopy\w*\b|\bai\b|\btechnical writ|\bseo\b|\baeo\b|\bgeo\b|\bsearch\b"
    r"|\bweb\b|\bcontent systems\b", re.I
)

# Flat list of every include term, exported so callers can build a cheap
# prefilter from the same source of truth rather than retyping the lists.
ALL_INCLUDE_TERMS: list[str] = (
    PRIMARY_AI_TITLES
    + PRIMARY_COPY_TITLES
    + CONDITIONAL_COPY_LEADERSHIP
    + SEARCH_AND_WEB_TITLES
    + CONDITIONAL_TITLES
)

_INCLUDE_GROUPS = {
    "ai": PRIMARY_AI_TITLES,
    "copy": PRIMARY_COPY_TITLES,
    "copy_leadership": CONDITIONAL_COPY_LEADERSHIP,
    "search_web": SEARCH_AND_WEB_TITLES,
    "conditional": CONDITIONAL_TITLES,
}


def _phrase(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)", re.I)


_COMPILED_INCLUDES = {
    group: [(term, _phrase(term)) for term in terms]
    for group, terms in _INCLUDE_GROUPS.items()
}


@dataclass(frozen=True)
class TitleVerdict:
    included: bool
    group: str | None
    matched: str | None
    excluded_by: str | None


def classify_title(title: str) -> TitleVerdict:
    """Apply title exclusions, then title inclusion. Exclusion always wins."""
    for pattern, label in _EXCLUSIONS:
        if pattern.search(title):
            return TitleVerdict(False, None, None, label)

    # These two families are rejected *unless* the title names an accepted
    # specialism. A rescued title has earned review, not silence: "Content
    # Manager, SEO" is neither an automatic reject nor a phrase on any include
    # list, and dropping it on the floor would lose exactly the roles the
    # rescue clause exists to keep.
    if _GENERIC_CREATIVE.search(title):
        if not _CREATIVE_RESCUE.search(title):
            return TitleVerdict(False, None, None, "generic creative leadership")
        return TitleVerdict(True, "conditional", "rescued creative leadership", None)

    if _GENERIC_CONTENT.search(title):
        if not _CONTENT_RESCUE.search(title):
            return TitleVerdict(False, None, None, "generic content role")
        return TitleVerdict(True, "conditional", "rescued content role", None)

    for group, terms in _COMPILED_INCLUDES.items():
        for term, pattern in terms:
            if pattern.search(title):
                return TitleVerdict(True, group, term, None)

    return TitleVerdict(False, None, None, "no title keyword matched")
