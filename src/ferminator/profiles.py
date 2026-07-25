"""Named Markdown profile parsing, validation, and compilation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CompensationRule(BaseModel):
    currency: str = "USD"
    minimum_base_annual: float | None = Field(default=None, ge=0)


class TargetTitles(BaseModel):
    high: list[str] = Field(default_factory=list)
    adjacent: list[str] = Field(default_factory=list)


class SearchRules(BaseModel):
    enabled: bool = True
    scan_interval_hours: int = Field(default=12, ge=1, le=168)
    default_geography: list[str] = Field(default_factory=lambda: ["Remote — United States"])
    allow_jobs_without_compensation: bool = True
    compensation: CompensationRule = Field(default_factory=CompensationRule)
    employment_types: list[str] = Field(default_factory=lambda: ["full-time"])
    target_seniority: list[str] = Field(default_factory=list)
    target_titles: TargetTitles = Field(default_factory=TargetTitles)
    require_title_match: bool = True
    enforce_default_geography: bool = True
    adjacent_minimum_preferred_hits: int = Field(default=1, ge=0, le=20)
    required_any: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)
    exclude: dict[str, list[str]] = Field(default_factory=dict)


class NotificationRules(BaseModel):
    dashboard: bool = True
    email: bool = True
    review_minimum_score: float = Field(default=58, ge=0, le=100)
    minimum_score: float = Field(default=70, ge=0, le=100)
    exceptional_score: float = Field(default=88, ge=0, le=100)
    max_daily_matches: int = Field(default=12, ge=1, le=100)

    @model_validator(mode="after")
    def exceptional_is_higher(self) -> NotificationRules:
        if self.review_minimum_score >= self.minimum_score:
            raise ValueError("review_minimum_score must be lower than minimum_score")
        if self.exceptional_score < self.minimum_score:
            raise ValueError("exceptional_score must be at least minimum_score")
        return self


class ProfileIdentity(BaseModel):
    slug: str
    display_name: str
    email_env: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", value):
            raise ValueError("profile slug must be lowercase letters, numbers, or hyphens")
        return value


class CareerProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(ge=1)
    profile: ProfileIdentity
    search: SearchRules
    notifications: NotificationRules = Field(default_factory=NotificationRules)
    scoring: dict[str, float]
    markdown_body: str
    source_path: Path
    source_hash: str

    @field_validator("scoring")
    @classmethod
    def scoring_totals_100(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("scoring weights are required")
        if any(weight < 0 for weight in value.values()):
            raise ValueError("scoring weights cannot be negative")
        total = sum(value.values())
        if abs(total - 100) > 0.01:
            raise ValueError(f"scoring weights must total 100, got {total:g}")
        return value

    @property
    def evidence_text(self) -> str:
        return re.sub(r"\s+", " ", self.markdown_body).strip()

    @property
    def high_titles(self) -> list[str]:
        return self.search.target_titles.high

    @property
    def adjacent_titles(self) -> list[str]:
        return self.search.target_titles.adjacent


def load_profile(path: str | Path) -> CareerProfile:
    """Load and validate a named profile from YAML-front-matter Markdown."""
    source_path = Path(path)
    raw = source_path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{source_path}: missing YAML front matter")
    try:
        _, front_matter, body = raw.split("---", 2)
    except ValueError as exc:
        raise ValueError(f"{source_path}: malformed YAML front matter") from exc
    data = yaml.safe_load(front_matter)
    if not isinstance(data, dict):
        raise ValueError(f"{source_path}: front matter must be a mapping")
    return CareerProfile.model_validate(
        {
            **data,
            "markdown_body": body.strip(),
            "source_path": source_path,
            "source_hash": hashlib.sha256(raw.encode()).hexdigest(),
        }
    )
