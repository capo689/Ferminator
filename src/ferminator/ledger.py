"""Application-ledger parsing and duplicate suppression rules."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_SUPPRESSION_DAYS = 183
_TITLE_VARIATION_TOKENS = {
    "enterprise", "global", "corporate", "senior", "sr", "junior", "jr", "staff",
}


def normalize_job_part(value: str) -> str:
    """Normalize company/title text without making location part of identity."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[®™©]", "", value)
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def job_fingerprint(company: str, title: str) -> str:
    return f"{normalize_job_part(company)}::{normalize_job_part(title)}"


@dataclass(frozen=True)
class PriorJobMatch:
    """A conservative, explainable near-match to prior job history."""

    likely_same_role: bool
    confidence: float
    reason: str


def compare_prior_job_titles(current_title: str, prior_title: str) -> PriorJobMatch:
    """Classify strong title variants while leaving near-matches visible."""
    current = normalize_job_part(current_title)
    prior = normalize_job_part(prior_title)
    if current == prior:
        return PriorJobMatch(True, 1.0, "Exact normalized title match")

    current_tokens = set(current.split())
    prior_tokens = set(prior.split())
    current_core = current_tokens - _TITLE_VARIATION_TOKENS
    prior_core = prior_tokens - _TITLE_VARIATION_TOKENS
    if len(current_core) >= 2 and current_core == prior_core:
        changed = ", ".join(sorted(current_tokens ^ prior_tokens)) or "minor wording"
        return PriorJobMatch(True, 0.96, f"Same core title; wording changed: {changed}")

    if not current_core or not prior_core:
        return PriorJobMatch(False, 0.0, "Insufficient title evidence")
    overlap = len(current_core & prior_core)
    containment = overlap / min(len(current_core), len(prior_core))
    jaccard = overlap / len(current_core | prior_core)
    sequence = SequenceMatcher(None, current, prior).ratio()
    confidence = round((containment * 0.55) + (jaccard * 0.25) + (sequence * 0.20), 2)
    likely = containment >= 0.8 and jaccard >= 0.6 and sequence >= 0.72
    return PriorJobMatch(
        likely,
        confidence if likely else 0.0,
        (
            f"Closely related title ({round(confidence * 100):d}% confidence)"
            if likely
            else "Titles are not similar enough"
        ),
    )


@dataclass(frozen=True)
class LedgerEntry:
    company: str
    title: str
    status: str
    category: str
    first_recorded_at: datetime
    suppress_until: datetime | None
    permanent: bool = False

    @property
    def fingerprint(self) -> str:
        return job_fingerprint(self.company, self.title)


@dataclass(frozen=True)
class CompanyWatch:
    company: str

    @property
    def normalized_company(self) -> str:
        return normalize_job_part(self.company)


@dataclass(frozen=True)
class ParsedLedger:
    entries: tuple[LedgerEntry, ...]
    company_watchlist: tuple[CompanyWatch, ...]


def _ledger_date(markdown: str) -> datetime:
    match = re.search(r"Last updated\s+(\d{4}-\d{2}-\d{2})", markdown)
    if not match:
        return datetime.now(UTC)
    return datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)


def parse_master_ledger(path: str | Path) -> ParsedLedger:
    """Parse the human-maintained Markdown ledger without losing its categories."""
    markdown = Path(path).read_text(encoding="utf-8")
    recorded_at = _ledger_date(markdown)
    category = ""
    entries: dict[str, LedgerEntry] = {}
    watchlist: list[CompanyWatch] = []
    in_watchlist = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^##\s+(.+?)(?:\s+\(\d+\))?$", line)
        if heading:
            category = heading.group(1).strip()
            in_watchlist = category.casefold() == "company watchlist"
            continue
        if in_watchlist and line and not line.startswith(("#", "|", "A prior", "These are")):
            for company in (part.strip() for part in line.split(",")):
                if company:
                    watchlist.append(CompanyWatch(company))
            in_watchlist = False
            continue
        if not line.startswith("|") or re.match(r"^\|[-:\s|]+\|$", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].casefold() == "company":
            continue
        company, title, status = cells[:3]
        if not company or not title:
            continue
        permanent = category.casefold() == "fake"
        entry = LedgerEntry(
            company=company,
            title=title,
            status=status or category,
            category=category,
            first_recorded_at=recorded_at,
            suppress_until=(
                None
                if permanent
                else recorded_at + timedelta(days=DEFAULT_SUPPRESSION_DAYS)
            ),
            permanent=permanent,
        )
        # Duplicate rows across sections collapse to the strongest/latest record.
        previous = entries.get(entry.fingerprint)
        if previous is None or category.casefold() == "applied":
            entries[entry.fingerprint] = entry

    return ParsedLedger(tuple(entries.values()), tuple(watchlist))
