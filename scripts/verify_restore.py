"""Verify the minimum relational integrity expected after an isolated restore."""

from __future__ import annotations

import json
import os
import sys

import psycopg
from psycopg.rows import dict_row

TABLES = (
    "profiles",
    "companies",
    "ats_boards",
    "ingestion_runs",
    "scan_runs",
    "jobs",
    "job_revisions",
    "job_matches",
    "job_actions",
    "job_history",
    "match_feedback",
)


def main() -> int:
    database_url = os.environ.get("RESTORE_DATABASE_URL")
    if not database_url:
        print("RESTORE_DATABASE_URL is required", file=sys.stderr)
        return 2
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        counts = {}
        for table in TABLES:
            counts[table] = connection.execute(
                f"select count(*) as count from public.{table}"  # noqa: S608
            ).fetchone()["count"]
        broken_revisions = connection.execute(
            """
            select count(*) as count
            from public.jobs j
            left join public.job_revisions r on r.id = j.current_revision_id
            where j.current_revision_id is not null and r.id is null
            """
        ).fetchone()["count"]
        orphaned_matches = connection.execute(
            """
            select count(*) as count
            from public.job_matches m
            left join public.jobs j on j.id = m.job_id
            left join public.profiles p on p.id = m.profile_id
            where j.id is null or p.id is null
            """
        ).fetchone()["count"]
    result = {
        "status": "ok" if not broken_revisions and not orphaned_matches else "failed",
        "row_counts": counts,
        "broken_current_revisions": broken_revisions,
        "orphaned_matches": orphaned_matches,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
