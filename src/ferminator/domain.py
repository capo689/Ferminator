"""Shared domain contracts for ATS ingestion and matching."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ATSProvider(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    WORKABLE = "workable"
    BAMBOOHR = "bamboohr"
    WORKDAY = "workday"
    BREEZY = "breezy"
    RIPPLING = "rippling"


class WorkplaceType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on-site"
    UNSPECIFIED = "unspecified"


class BoardRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ATSProvider
    company_slug: str
    company_name: str
    board_key: str
    source_url: HttpUrl
    region: str = "global"

    @field_validator("company_slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,126}", normalized):
            raise ValueError("company_slug must be lowercase letters, numbers, or hyphens")
        return normalized


class JobLocation(BaseModel):
    label: str
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    is_primary: bool = False
    is_remote: bool = False

    @property
    def normalized_key(self) -> str:
        return re.sub(r"\s+", " ", self.label.strip().lower())


class Compensation(BaseModel):
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)
    currency: str | None = None
    interval: str | None = None
    raw_text: str | None = None
    source: str = "structured"

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper()[:3] if value else None


_MONEY_VALUE = r"(?:\d{1,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?)\s*[kK]?"
_RANGE_PATTERN = re.compile(
    rf"(?P<currency1>USD|CAD|GBP|EUR|[$£€])?\s*"
    rf"(?P<minimum>{_MONEY_VALUE})\s*"
    rf"(?:-|–|—|to|through)\s*"
    rf"(?P<currency2>USD|CAD|GBP|EUR|[$£€])?\s*"
    rf"(?P<maximum>{_MONEY_VALUE})",
    re.IGNORECASE,
)
_SINGLE_PATTERN = re.compile(
    rf"(?P<currency>USD|CAD|GBP|EUR|[$£€])\s*(?P<value>{_MONEY_VALUE})",
    re.IGNORECASE,
)
_PAY_CONTEXT = (
    "base salary",
    "salary range",
    "salary",
    "annual salary",
    "annual base",
    "base pay",
    "pay range",
    "compensation range",
    "base compensation",
    "starting salary",
)


def _money_number(value: str) -> float:
    normalized = value.replace(",", "").replace(" ", "")
    multiplier = 1000 if normalized.casefold().endswith("k") else 1
    if multiplier == 1000:
        normalized = normalized[:-1]
    return float(normalized) * multiplier


def _currency_code(*markers: str | None) -> str:
    marker = next((item for item in markers if item), "$").upper()
    return {"$": "USD", "£": "GBP", "€": "EUR"}.get(marker, marker)


def extract_compensation_from_text(value: str | None) -> Compensation | None:
    """Extract a conservative published pay range from a complete job description."""
    if not value:
        return None
    text = re.sub(r"\s+", " ", value)
    candidates: list[tuple[int, int, Compensation]] = []
    for match in _RANGE_PATTERN.finditer(text):
        before = text[max(0, match.start() - 120):match.start()].casefold()
        after = text[match.end():min(len(text), match.end() + 70)].casefold()
        context = f"{before} {after}"
        has_pay_context = any(term in context for term in _PAY_CONTEXT)
        has_currency = bool(match.group("currency1") or match.group("currency2"))
        if not (has_pay_context or has_currency):
            continue
        minimum = _money_number(match.group("minimum"))
        maximum = _money_number(match.group("maximum"))
        interval = "hour" if re.search(r"(?:per|/)\s*(?:hour|hr)\b|hourly", after) else "year"
        if interval == "year" and (minimum < 10_000 or maximum > 2_000_000):
            continue
        if interval == "hour" and (minimum > 1000 or maximum > 1000):
            continue
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        context_score = 3 if has_pay_context else 1
        if "base" in context:
            context_score += 2
        if "total compensation" in before[-50:] or "ote" in before[-30:]:
            context_score -= 2
        candidates.append(
            (
                context_score,
                -match.start(),
                Compensation(
                    minimum=minimum,
                    maximum=maximum,
                    currency=_currency_code(
                        match.group("currency1"),
                        match.group("currency2"),
                    ),
                    interval=interval,
                    raw_text=match.group(0).strip(),
                    source="description",
                ),
            )
        )
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[2]

    for match in _SINGLE_PATTERN.finditer(text):
        before = text[max(0, match.start() - 100):match.start()].casefold()
        after = text[match.end():min(len(text), match.end() + 50)].casefold()
        if not any(term in f"{before} {after}" for term in _PAY_CONTEXT):
            continue
        amount = _money_number(match.group("value"))
        interval = "hour" if re.search(r"(?:per|/)\s*(?:hour|hr)\b|hourly", after) else "year"
        if interval == "year" and not 10_000 <= amount <= 2_000_000:
            continue
        return Compensation(
            minimum=amount,
            maximum=amount,
            currency=_currency_code(match.group("currency")),
            interval=interval,
            raw_text=match.group(0).strip(),
            source="description",
        )
    return None


class NormalizedJob(BaseModel):
    provider: ATSProvider
    board_key: str
    source_job_id: str
    company_slug: str
    company_name: str
    title: str
    description_text: str = ""
    description_html: str | None = None
    department: str | None = None
    team: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    workplace_type: WorkplaceType = WorkplaceType.UNSPECIFIED
    locations: list[JobLocation] = Field(default_factory=list)
    compensation: Compensation | None = None
    job_url: HttpUrl
    apply_url: HttpUrl | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_job_id", mode="before")
    @classmethod
    def stringify_id(cls, value: Any) -> str:
        return str(value)

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            raise ValueError("job title cannot be empty")
        return value

    @field_validator("published_at", "source_updated_at", "retrieved_at", mode="after")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None

    @property
    def source_key(self) -> str:
        return f"{self.provider.value}:{self.board_key}:{self.source_job_id}"

    @property
    def search_document(self) -> str:
        values = [
            self.title,
            self.company_name,
            self.department or "",
            self.team or "",
            self.employment_type or "",
            self.workplace_type.value,
            " ".join(location.label for location in self.locations),
            self.description_text,
        ]
        return re.sub(r"\s+", " ", " ".join(values)).strip()

    @property
    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"retrieved_at"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def html_to_text(value: str | None) -> str:
    """Convert provider HTML into stable normalized plain text."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def as_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime, interpreting naive provider values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(value: Any) -> datetime | None:
    """Parse common ISO timestamps without failing an entire provider run."""
    if not value:
        return None
    if isinstance(value, datetime):
        return as_utc(value)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return as_utc(datetime.fromisoformat(text))
    except ValueError:
        try:
            return datetime.fromtimestamp(float(text) / 1000, tz=UTC)
        except (ValueError, OverflowError):
            return None
