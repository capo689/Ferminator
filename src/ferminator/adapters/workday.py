"""Workday public career-site adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ferminator.adapters.base import BaseAdapter
from ferminator.domain import ATSProvider, BoardRef, JobLocation, NormalizedJob, WorkplaceType


class WorkdayAdapter(BaseAdapter):
    provider = ATSProvider.WORKDAY
    page_size = 20
    max_jobs = 5000

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        tenant, site = board.board_key.split("/", 1)
        origin = f"{urlsplit(str(board.source_url)).scheme}://{urlsplit(str(board.source_url)).netloc}"
        endpoint = f"{origin}/wday/cxs/{tenant}/{site}/jobs"
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset < self.max_jobs:
            payload = self.post_json(
                endpoint,
                {
                    "appliedFacets": {},
                    "limit": self.page_size,
                    "offset": offset,
                    "searchText": "",
                },
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("jobPostings"), list):
                raise ValueError("Workday postings response is invalid")
            page = payload["jobPostings"]
            rows.extend(page)
            total = int(payload.get("total") or len(rows))
            if not page or len(rows) >= total:
                break
            offset += len(page)
        return [self.normalize(board, row, origin, tenant, site) for row in rows]

    def normalize(
        self,
        board: BoardRef,
        row: dict[str, Any],
        origin: str | None = None,
        tenant: str | None = None,
        site: str | None = None,
    ) -> NormalizedJob:
        origin = origin or f"{urlsplit(str(board.source_url)).scheme}://{urlsplit(str(board.source_url)).netloc}"
        tenant, site = (tenant, site) if tenant and site else board.board_key.split("/", 1)
        external_path = row["externalPath"]
        location = row.get("locationsText") or "Unspecified"
        remote = "remote" in location.casefold()
        job_url = f"{origin}/{site}{external_path}"
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            # A requisition number can legitimately appear once per location.
            # The external posting path identifies the distinct public listing.
            source_job_id=external_path,
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row["title"],
            employment_type=row.get("timeType"),
            workplace_type=WorkplaceType.REMOTE if remote else WorkplaceType.UNSPECIFIED,
            locations=[JobLocation(label=location, is_primary=True, is_remote=remote)],
            job_url=job_url,
            apply_url=job_url,
            raw_metadata={
                "external_path": external_path,
                "posted_on": row.get("postedOn"),
                "requisition_id": (row.get("bulletFields") or [None])[0],
                "tenant": tenant,
                "site": site,
            },
        )
