"""SmartRecruiters public Posting API adapter."""

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


class SmartRecruitersAdapter(BaseAdapter):
    provider = ATSProvider.SMARTRECRUITERS

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.get_json(
                "https://api.smartrecruiters.com/v1/companies/"
                f"{board.board_key}/postings?limit=100&offset={offset}"
            )
            page = payload.get("content", [])
            if not isinstance(page, list):
                raise ValueError("SmartRecruiters content must be a list")
            rows.extend(page)
            offset += len(page)
            if not page or offset >= int(payload.get("totalFound", len(rows))):
                break
        return [self._fetch_and_normalize(board, row) for row in rows]

    def _fetch_and_normalize(
        self, board: BoardRef, summary: dict[str, Any]
    ) -> NormalizedJob:
        job_id = summary.get("id") or summary.get("uuid")
        detail = self.get_json(
            "https://api.smartrecruiters.com/v1/companies/"
            f"{board.board_key}/postings/{job_id}"
        )
        return self.normalize(board, {**summary, **detail})

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        location = row.get("location") or {}
        label = ", ".join(
            str(location.get(key))
            for key in ("city", "region", "country")
            if location.get(key)
        )
        job_id = row.get("id") or row.get("uuid")
        sections = row.get("jobAd", {}).get("sections", {})
        description_html = " ".join(
            section.get("text", "")
            for section in sections.values()
            if isinstance(section, dict)
        )
        remote = "remote" in label.casefold() or bool(location.get("remote"))
        job_url = row.get("postingUrl") or f"https://jobs.smartrecruiters.com/{board.board_key}/{job_id}"
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=job_id,
            company_slug=board.company_slug,
            company_name=(row.get("company") or {}).get("name") or board.company_name,
            title=row.get("name") or row.get("defaultJobAd", {}).get("title"),
            description_text=html_to_text(description_html),
            description_html=description_html or None,
            department=(row.get("department") or {}).get("label"),
            employment_type=(row.get("typeOfEmployment") or {}).get("label"),
            seniority=(row.get("experienceLevel") or {}).get("label"),
            workplace_type=WorkplaceType.REMOTE if remote else WorkplaceType.UNSPECIFIED,
            locations=[JobLocation(
                label=label,
                city=location.get("city"),
                region=location.get("region"),
                country=location.get("country"),
                country_code=location.get("countryCode"),
                is_primary=True,
                is_remote=remote,
            )]
            if label else [],
            job_url=job_url,
            apply_url=job_url,
            published_at=parse_datetime(row.get("releasedDate")),
        )
