"""BambooHR public careers JSON adapter."""

from __future__ import annotations

import time
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


class BambooHRAdapter(BaseAdapter):
    provider = ATSProvider.BAMBOOHR
    detail_delay_seconds = 0.25

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        base = f"https://{board.board_key}.bamboohr.com/careers"
        payload = self.get_json(f"{base}/list")
        rows = payload.get("result", [])
        if not isinstance(rows, list):
            raise ValueError("BambooHR result must be a list")
        jobs = []
        for index, summary in enumerate(rows):
            detail = self.get_json(f"{base}/{summary['id']}/detail")
            opening = (detail.get("result") or {}).get("jobOpening") or {}
            jobs.append(self.normalize(board, {**summary, **opening}))
            if index < len(rows) - 1:
                time.sleep(self.detail_delay_seconds)
        return jobs

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        ats_location = row.get("atsLocation") or row.get("location") or {}
        if isinstance(ats_location, str):
            label = ats_location
            ats_location = {}
        else:
            country = ats_location.get("country") or ats_location.get("addressCountry")
            region = ats_location.get("state") or ats_location.get("addressRegion")
            label = ", ".join(
                str(value)
                for value in (ats_location.get("city"), region, country)
                if value
            )
        label = label or "Remote"
        location_type = str(row.get("locationType", "")).casefold()
        remote = bool(row.get("isRemote")) or location_type in {
            "1",
            "remote",
            "fully remote",
        }
        workplace = (
            WorkplaceType.REMOTE if remote
            else WorkplaceType.HYBRID if location_type in {"2", "hybrid"}
            else WorkplaceType.ON_SITE
        )
        raw_comp = row.get("compensation")
        compensation = Compensation(raw_text=str(raw_comp)) if raw_comp else None
        job_id = row["id"]
        job_url = row.get("jobOpeningShareUrl") or (
            f"https://{board.board_key}.bamboohr.com/careers/{job_id}"
        )
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=job_id,
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row.get("jobOpeningName") or row.get("title"),
            description_text=html_to_text(row.get("description")),
            description_html=row.get("description"),
            department=row.get("departmentLabel"),
            employment_type=row.get("employmentStatusLabel"),
            seniority=row.get("minimumExperience"),
            workplace_type=workplace,
            locations=[
                JobLocation(
                    label=label,
                    city=ats_location.get("city"),
                    region=ats_location.get("state") or ats_location.get("addressRegion"),
                    country=ats_location.get("country") or ats_location.get("addressCountry"),
                    is_primary=True,
                    is_remote=remote,
                )
            ],
            compensation=compensation,
            job_url=job_url,
            apply_url=job_url,
            published_at=parse_datetime(row.get("datePosted")),
        )
