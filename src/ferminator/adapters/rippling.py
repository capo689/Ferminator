"""Rippling public board adapter using its server-rendered data."""

from __future__ import annotations

import json
import re
from typing import Any

from ferminator.adapters.base import AdapterError, BaseAdapter
from ferminator.domain import ATSProvider, BoardRef, JobLocation, NormalizedJob, WorkplaceType

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class RipplingAdapter(BaseAdapter):
    provider = ATSProvider.RIPPLING

    def fetch_jobs(self, board: BoardRef) -> list[NormalizedJob]:
        html = self.get_text(str(board.source_url))
        match = _NEXT_DATA.search(html)
        if not match:
            raise AdapterError("embedded_data_missing", "Rippling board data was missing")
        try:
            payload = json.loads(match.group(1))
            queries = payload["props"]["pageProps"]["dehydratedState"]["queries"]
            data = next(
                query["state"]["data"]
                for query in queries
                if isinstance(query.get("state", {}).get("data"), dict)
                and isinstance(query["state"]["data"].get("items"), list)
                and (
                    not query["state"]["data"]["items"]
                    or "url" in query["state"]["data"]["items"][0]
                )
            )
        except (json.JSONDecodeError, KeyError, StopIteration, TypeError) as exc:
            raise AdapterError(
                "embedded_data_invalid",
                "Rippling board data was invalid",
            ) from exc
        unique_rows = {row["id"]: row for row in data["items"]}
        return [self.normalize(board, row) for row in unique_rows.values()]

    def normalize(self, board: BoardRef, row: dict[str, Any]) -> NormalizedJob:
        locations = [
            JobLocation(
                label=location.get("name") or "Unspecified",
                city=location.get("city"),
                region=location.get("stateCode") or location.get("state"),
                country=location.get("country"),
                country_code=location.get("countryCode"),
                is_primary=index == 0,
                is_remote=location.get("workplaceType") == "REMOTE",
            )
            for index, location in enumerate(row.get("locations") or [])
        ]
        workplace_values = {
            location.get("workplaceType") for location in row.get("locations") or []
        }
        workplace = (
            WorkplaceType.REMOTE
            if "REMOTE" in workplace_values
            else WorkplaceType.HYBRID
            if "HYBRID" in workplace_values
            else WorkplaceType.ON_SITE
            if "ON_SITE" in workplace_values
            else WorkplaceType.UNSPECIFIED
        )
        return NormalizedJob(
            provider=self.provider,
            board_key=board.board_key,
            source_job_id=row["id"],
            company_slug=board.company_slug,
            company_name=board.company_name,
            title=row["name"],
            department=(row.get("department") or {}).get("name"),
            workplace_type=workplace,
            locations=locations,
            job_url=row["url"],
            apply_url=row["url"],
            raw_metadata={"language": row.get("language")},
        )
