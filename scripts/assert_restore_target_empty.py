"""Refuse recovery unless the destination is an empty, isolated database."""

from __future__ import annotations

import os
import sys

import psycopg

FERMINATOR_TABLES = (
    "profiles",
    "jobs",
    "job_revisions",
    "job_matches",
    "job_actions",
    "job_history",
)


def main() -> int:
    database_url = os.environ.get("RESTORE_DATABASE_URL")
    if not database_url:
        print("RESTORE_DATABASE_URL is required", file=sys.stderr)
        return 2
    with psycopg.connect(database_url) as connection:
        existing = connection.execute(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public' and table_name = any(%s)
            order by table_name
            """,
            (list(FERMINATOR_TABLES),),
        ).fetchall()
    if existing:
        print("Restore target already contains Ferminator tables; refusing", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
