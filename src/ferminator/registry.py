"""Curated company and ATS board registry."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from ferminator.domain import ATSProvider, BoardRef


class RegistryBoard(BaseModel):
    provider: ATSProvider
    board_key: str
    source_url: HttpUrl
    region: str = "global"
    enabled: bool = True


class RegistryCompany(BaseModel):
    slug: str
    name: str
    website_url: HttpUrl | None = None
    career_url: HttpUrl | None = None
    enabled: bool = True
    priority: int = Field(default=0, ge=-100, le=100)
    boards: list[RegistryBoard]

    @model_validator(mode="after")
    def has_board(self) -> RegistryCompany:
        if not self.boards:
            raise ValueError("company must define at least one ATS board")
        return self

    def board_refs(self) -> list[BoardRef]:
        if not self.enabled:
            return []
        return [
            BoardRef(
                provider=board.provider,
                company_slug=self.slug,
                company_name=self.name,
                board_key=board.board_key,
                source_url=board.source_url,
                region=board.region,
            )
            for board in self.boards
            if board.enabled
        ]


class CompanyRegistry(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(ge=1)
    companies: list[RegistryCompany]

    @model_validator(mode="after")
    def unique_sources(self) -> CompanyRegistry:
        slugs = [company.slug for company in self.companies]
        if len(slugs) != len(set(slugs)):
            raise ValueError("company slugs must be unique")
        keys = [
            (board.provider, board.board_key, board.region)
            for company in self.companies
            for board in company.boards
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("ATS provider/board/region combinations must be unique")
        return self

    @property
    def enabled_boards(self) -> list[BoardRef]:
        companies = sorted(
            self.companies,
            key=lambda company: (-company.priority, company.name.casefold()),
        )
        return [board for company in companies for board in company.board_refs()]


def load_registry(path: str | Path = "config/companies.yaml") -> CompanyRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("company registry must be a mapping")
    return CompanyRegistry.model_validate(payload)

