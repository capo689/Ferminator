"""Lever public Postings API adapter."""

from __future__ import annotations

from typing import Any

from ferminator.adapters.base import BaseAdapter
from ferminator.domain import (
    ATSProvider,
    BoardRef,
    Compensation,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
    html_to_text,
    parse_datetime,
)


class LeverAdapter(BaseAdapter):
    provider = ATSProvider.LEVER

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        host = "api.eu.lever.co" if board.region == "eu" else "api.lever.co"
        payload = self.get_json(
            f"https://{host}/v0/postings/{board.board_key}?mode=json"
        )
        if not isinstance(payload, list):
            raise ValueError("Lever postings must be a list")
        return [self.normalize(board, row) for row in payload]

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        categories = row.get("categories") or {}
        location_labels = categories.get("allLocations") or [categories.get("location")]
        locations = [
            JobLocation(
                label=value,
                is_primary=index == 0,
                is_remote="remote" in value.casefold(),
            )
            for index, value in enumerate(location_labels)
            if value
        ]
        workplace = {
            "remote": WorkplaceType.REMOTE,
            "hybrid": WorkplaceType.HYBRID,
            "on-site": WorkplaceType.ON_SITE,
        }.get(row.get("workplaceType"), WorkplaceType.UNSPECIFIED)
        salary = row.get("salaryRange")
        compensation = Compensation(
            minimum=salary.get("min"),
            maximum=salary.get("max"),
            currency=salary.get("currency"),
            interval=salary.get("interval"),
            raw_text=row.get("salaryDescriptionPlain"),
        ) if salary else None
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=row["id"],
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row["text"],
            description_text=row.get("descriptionPlain") or html_to_text(row.get("description")),
            description_html=row.get("description"),
            department=categories.get("department"),
            team=categories.get("team"),
            employment_type=categories.get("commitment"),
            seniority=categories.get("level"),
            workplace_type=workplace,
            locations=locations,
            compensation=compensation,
            job_url=row["hostedUrl"],
            apply_url=row.get("applyUrl"),
            published_at=parse_datetime(row.get("createdAt")),
        )

