"""Ashby public job-board API adapter."""

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
    parse_datetime,
)


class AshbyAdapter(BaseAdapter):
    provider = ATSProvider.ASHBY

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        payload = self.get_json(
            "https://api.ashbyhq.com/posting-api/job-board/"
            f"{board.board_key}?includeCompensation=true"
        )
        rows = payload.get("jobs", [])
        if not isinstance(rows, list):
            raise ValueError("Ashby jobs must be a list")
        return [self.normalize(board, row) for row in rows if row.get("isListed", True)]

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        locations = []
        if row.get("location"):
            locations.append(
                JobLocation(
                    label=row["location"],
                    is_primary=True,
                    is_remote=bool(row.get("isRemote")),
                )
            )
        for secondary in row.get("secondaryLocations") or []:
            if secondary.get("location"):
                locations.append(JobLocation(label=secondary["location"]))
        workplace = {
            "Remote": WorkplaceType.REMOTE,
            "Hybrid": WorkplaceType.HYBRID,
            "OnSite": WorkplaceType.ON_SITE,
            "On-site": WorkplaceType.ON_SITE,
        }.get(row.get("workplaceType"), WorkplaceType.UNSPECIFIED)
        comp = row.get("compensation") or {}
        compensation = None
        if comp:
            compensation = Compensation(
                minimum=comp.get("minValue"),
                maximum=comp.get("maxValue"),
                currency=comp.get("currencyCode"),
                interval=comp.get("interval"),
                raw_text=comp.get("scrapeableCompensationSalarySummary"),
            )
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=row["id"],
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row["title"],
            description_text=row.get("descriptionPlain") or "",
            description_html=row.get("descriptionHtml"),
            department=row.get("department"),
            team=row.get("team"),
            employment_type=row.get("employmentType"),
            workplace_type=workplace,
            locations=locations,
            compensation=compensation,
            job_url=row["jobUrl"],
            apply_url=row.get("applyUrl"),
            published_at=parse_datetime(row.get("publishedAt")),
        )

