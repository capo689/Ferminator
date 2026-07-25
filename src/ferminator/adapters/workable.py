"""Workable public careers endpoint adapter."""

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


class WorkableAdapter(BaseAdapter):
    provider = ATSProvider.WORKABLE

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        payload = self.get_json(
            f"https://www.workable.com/api/accounts/{board.board_key}?details=true"
        )
        rows = payload.get("jobs", [])
        if not isinstance(rows, list):
            raise ValueError("Workable jobs must be a list")
        return [self.normalize(board, row) for row in rows]

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        location_values = row.get("locations") or []
        if not location_values and row.get("city"):
            location_values = [
                {
                    "city": row.get("city"),
                    "region": row.get("state"),
                    "country": row.get("country"),
                }
            ]
        remote = bool(row.get("telecommuting"))
        locations = []
        for index, item in enumerate(location_values):
            if isinstance(item, str):
                label = item
                values = {}
            else:
                values = item
                label = ", ".join(
                    str(values.get(key))
                    for key in ("city", "region", "country", "country_name")
                    if values.get(key)
                )
            if label:
                locations.append(
                    JobLocation(
                        label=label,
                        city=values.get("city"),
                        region=values.get("region"),
                        country=values.get("country") or values.get("country_name"),
                        is_primary=index == 0,
                        is_remote=remote,
                    )
                )
        salary = row.get("salary") or {}
        compensation = Compensation(
            minimum=salary.get("salary_from"),
            maximum=salary.get("salary_to"),
            currency=salary.get("salary_currency"),
        ) if salary else None
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=row.get("shortcode") or row.get("id"),
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row["title"],
            description_text=html_to_text(row.get("description")),
            description_html=row.get("description"),
            department=row.get("department"),
            employment_type=row.get("employment_type"),
            workplace_type=WorkplaceType.REMOTE if remote else WorkplaceType.UNSPECIFIED,
            locations=locations,
            compensation=compensation,
            job_url=row.get("url") or row["shortlink"],
            apply_url=row.get("application_url") or row.get("shortlink"),
            published_at=parse_datetime(row.get("published_on") or row.get("created_at")),
        )

