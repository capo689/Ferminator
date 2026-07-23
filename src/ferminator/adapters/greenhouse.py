"""Greenhouse public Job Board API adapter."""

from __future__ import annotations

from typing import Any

from ferminator.adapters.base import BaseAdapter
from ferminator.domain import (
    ATSProvider,
    BoardRef,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
    html_to_text,
    parse_datetime,
)


class GreenhouseAdapter(BaseAdapter):
    provider = ATSProvider.GREENHOUSE

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board.board_key}/jobs?content=true"
        payload = self.get_json(url)
        rows = payload.get("jobs", [])
        if not isinstance(rows, list):
            raise ValueError("Greenhouse jobs must be a list")
        return [self.normalize(board, row) for row in rows]

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        raw_location = (row.get("location") or {}).get("name", "")
        locations = [
            JobLocation(
                label=raw_location,
                is_primary=True,
                is_remote="remote" in raw_location.casefold(),
            )
        ] if raw_location else []
        departments = row.get("departments") or []
        department = departments[0].get("name") if departments else None
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=row["id"],
            company_slug=board.company_slug,
            company_name=row.get("company_name") or board.company_name,
            title=row["title"],
            description_text=html_to_text(row.get("content")),
            description_html=row.get("content"),
            department=department,
            workplace_type=(
                WorkplaceType.REMOTE
                if "remote" in raw_location.casefold()
                else WorkplaceType.UNSPECIFIED
            ),
            locations=locations,
            job_url=row["absolute_url"],
            apply_url=row["absolute_url"],
            published_at=parse_datetime(row.get("first_published")),
            source_updated_at=parse_datetime(row.get("updated_at")),
            raw_metadata={"requisition_id": row.get("requisition_id")},
        )

