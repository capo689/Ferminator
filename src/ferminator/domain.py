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

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper()[:3] if value else None


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
