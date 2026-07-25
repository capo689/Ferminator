"""One-off backfill: parse salary data for every active job in the DB.

Normally only newly-added jobs get their salary parsed (see cli.fetch).
This script iterates over every active job and populates compensation.
"""

import os
import sqlite3
import sys

from anthropic_tracker.config import get_companies, get_db_path
from anthropic_tracker.fetcher import fetch_job_details_batch
from anthropic_tracker.parser import parse_compensation


def main() -> int:
    company = os.environ.get("TRACKER_COMPANY") or get_companies()[0]
    db_path = get_db_path(company=company)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id FROM jobs WHERE removed_date IS NULL"
    ).fetchall()
    job_ids = [r["id"] for r in rows]
    print(f"Backfilling salaries for {len(job_ids)} active jobs ('{company}')...")

    details = fetch_job_details_batch(company, job_ids)
    parsed = 0
    for detail in details:
        content = detail.get("content", "")
        if not content:
            continue
        comp = parse_compensation(content)
        if not comp:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO compensation
               (job_id, salary_min, salary_max, currency, comp_type, raw_text)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                detail["id"],
                comp["salary_min"],
                comp["salary_max"],
                comp["currency"],
                comp["comp_type"],
                comp["raw_text"],
            ),
        )
        parsed += 1
    conn.commit()
    print(f"Parsed compensation for {parsed}/{len(job_ids)} jobs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
