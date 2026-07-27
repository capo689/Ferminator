"""Workday public career-site adapter."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from ferminator.adapters.base import BaseAdapter
from ferminator.domain import ATSProvider, BoardRef, JobLocation, NormalizedJob, WorkplaceType

logger = logging.getLogger("ferminator.adapters.workday")


def _is_normalizable(row: Any) -> bool:
    """A posting is usable only if it carries the fields normalize() requires."""
    return (
        isinstance(row, dict)
        and isinstance(row.get("externalPath"), str)
        and row["externalPath"].strip() != ""
        and isinstance(row.get("title"), str)
        and row["title"].strip() != ""
    )


class WorkdayAdapter(BaseAdapter):
    provider = ATSProvider.WORKDAY
    page_size = 20
    max_jobs = 5000

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        tenant, site = board.board_key.split("/", 1)
        origin = f"{urlsplit(str(board.source_url)).scheme}://{urlsplit(str(board.source_url)).netloc}"
        endpoint = f"{origin}/wday/cxs/{tenant}/{site}/jobs"
        rows: list[dict[str, Any]] = []
        total: int | None = None
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
            # Workday reports the real total only on the first page and sends 0
            # afterwards. `payload.get("total") or len(rows)` therefore fell back
            # to the row count from page two onward, making `len(rows) >= total`
            # trivially true and stopping every board at exactly 40 jobs. Keep
            # the first non-zero total and page until it is satisfied.
            page_total = payload.get("total")
            if total is None and isinstance(page_total, int) and page_total > 0:
                total = page_total
            if not page:
                break
            if total is not None and len(rows) >= total:
                break
            # Without a usable total, a short page is the end of the board.
            if total is None and len(page) < self.page_size:
                break
            offset += len(page)
        # Workday postings are not uniformly shaped: some tenants omit fields
        # others always send. normalize() needs externalPath and title, and one
        # malformed posting anywhere in a 2,000-job board used to raise KeyError
        # and abort the entire fetch, so the board ingested nothing at all.
        # Skip the unusable rows and keep the board.
        usable = [row for row in rows if _is_normalizable(row)]
        skipped = len(rows) - len(usable)
        if skipped:
            logger.warning(
                "workday_postings_skipped",
                extra={
                    "event": "workday_postings_skipped",
                    "board_key": board.board_key,
                    "skipped": skipped,
                    "kept": len(usable),
                },
            )
        if rows and not usable:
            raise ValueError("Workday returned no usable postings")
        return [self.normalize(board, row, origin, tenant, site) for row in usable]

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
