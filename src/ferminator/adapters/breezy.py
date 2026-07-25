"""Breezy HR public board adapter."""

from __future__ import annotations

from typing import Any

from ferminator.adapters.base import BaseAdapter
from ferminator.domain import (
    ATSProvider,
    BoardRef,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
    parse_datetime,
)


class BreezyAdapter(BaseAdapter):
    provider = ATSProvider.BREEZY

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        payload = self.get_json(f"{str(board.source_url).rstrip('/')}/json")
        if not isinstance(payload, list):
            raise ValueError("Breezy postings must be a list")
        return [self.normalize(board, row) for row in payload]

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        raw_locations = row.get("locations") or [row.get("location") or {}]
        locations = [
            JobLocation(
                label=location.get("name") or "Unspecified",
                city=location.get("city"),
                region=(location.get("state") or {}).get("id"),
                country=(location.get("country") or {}).get("name"),
                country_code=(location.get("country") or {}).get("id"),
                is_primary=bool(location.get("primary", index == 0)),
                is_remote=bool(location.get("is_remote")),
            )
            for index, location in enumerate(raw_locations)
            if location
        ]
        is_remote = any(location.is_remote for location in locations)
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=row["id"],
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row["name"],
            department=row.get("department"),
            employment_type=(row.get("type") or {}).get("name"),
            workplace_type=WorkplaceType.REMOTE if is_remote else WorkplaceType.UNSPECIFIED,
            locations=locations,
            job_url=row["url"],
            apply_url=row["url"],
            published_at=parse_datetime(row.get("published_date")),
            raw_metadata={"salary_text": row.get("salary") or None},
        )
