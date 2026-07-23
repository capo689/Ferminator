"""Snapshot diffing and delta computation."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from anthropic_tracker.parser import parse_locations


@dataclass
class DeltaResult:
    """Result of comparing current API data against the last stored snapshot."""

    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    unchanged: int = 0
    total: int = 0
    departments: dict[str, int] = field(default_factory=dict)
    locations: dict[str, int] = field(default_factory=dict)


def compute_delta(
    conn: sqlite3.Connection,
    current_jobs: list[dict],
    snapshot_date: str | None = None,
) -> DeltaResult:
    """Compare current API jobs against DB state, update DB, return delta.

    This is the core operation: it upserts jobs, marks removals,
    computes breakdowns, and writes the daily snapshot row.

    Wrapped in a single transaction so a mid-fetch failure leaves the DB
    in its prior consistent state instead of partially applying the delta.
    """
    try:
        return _compute_delta_inner(conn, current_jobs, snapshot_date)
    except Exception:
        conn.rollback()
        raise


def _compute_delta_inner(
    conn: sqlite3.Connection,
    current_jobs: list[dict],
    snapshot_date: str | None,
) -> DeltaResult:
    today = snapshot_date or date.today().isoformat()
    result = DeltaResult(total=len(current_jobs))

    # Current active job IDs from DB
    db_active = {
        row["id"]
        for row in conn.execute("SELECT id FROM jobs WHERE is_active = 1").fetchall()
    }
    api_ids = {job["id"] for job in current_jobs}

    added_ids = api_ids - db_active
    removed_ids = db_active - api_ids

    # Process each current job
    for job in current_jobs:
        job_id = job["id"]
        dept = _extract_department(job)
        loc_raw = job.get("location", {}).get("name", "")

        if job_id in added_ids:
            _insert_job(conn, job, today, dept, loc_raw)
            result.added.append({"id": job_id, "title": job["title"], "department": dept["name"]})
        else:
            # Update last_seen for existing jobs
            conn.execute("UPDATE jobs SET last_seen = ? WHERE id = ?", (today, job_id))

        # Count departments and locations
        dept_name = dept["name"]
        result.departments[dept_name] = result.departments.get(dept_name, 0) + 1

        for loc in parse_locations(loc_raw):
            result.locations[loc] = result.locations.get(loc, 0) + 1

    # Mark removed jobs
    for job_id in removed_ids:
        conn.execute(
            "UPDATE jobs SET is_active = 0, removed_date = ? WHERE id = ?",
            (today, job_id),
        )
        row = conn.execute(
            "SELECT id, title, department_id FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row:
            dept_row = conn.execute(
                "SELECT name FROM departments WHERE id = ?", (row["department_id"],)
            ).fetchone()
            dept_name = dept_row["name"] if dept_row else "Unknown"
            result.removed.append({"id": row["id"], "title": row["title"], "department": dept_name})

    result.unchanged = result.total - len(result.added)

    # Write daily snapshot
    response_hash = hashlib.sha256(
        json.dumps([j["id"] for j in current_jobs], sort_keys=True).encode()
    ).hexdigest()

    conn.execute(
        """INSERT OR REPLACE INTO daily_snapshots
           (date, total_active_jobs, jobs_added, jobs_removed,
            departments_json, locations_json, raw_response_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            today,
            result.total,
            len(result.added),
            len(result.removed),
            json.dumps(result.departments, sort_keys=True),
            json.dumps(result.locations, sort_keys=True),
            response_hash,
        ),
    )

    conn.commit()
    return result


def _extract_department(job: dict) -> dict:
    """Extract the primary department from a job dict."""
    departments = job.get("departments", [])
    if departments:
        return {"id": departments[0].get("id"), "name": departments[0].get("name", "Unknown")}
    return {"id": None, "name": "Unknown"}


def _insert_job(
    conn: sqlite3.Connection,
    job: dict,
    today: str,
    dept: dict,
    loc_raw: str,
) -> None:
    """Insert a new job and its related records."""
    # Upsert department
    if dept["id"]:
        conn.execute(
            """INSERT INTO departments (id, name, first_seen, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET last_seen = ?, name = ?""",
            (dept["id"], dept["name"], today, today, today, dept["name"]),
        )

    # Upsert offices
    for office in job.get("offices", []):
        office_loc = office.get("location", {})
        if isinstance(office_loc, dict):
            office_loc_name = office_loc.get("name", "")
        else:
            office_loc_name = str(office_loc) if office_loc else ""
        conn.execute(
            """INSERT INTO offices (id, name, location, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET last_seen = ?, name = ?""",
            (office["id"], office["name"], office_loc_name, today, today, today, office["name"]),
        )

    # Insert job
    conn.execute(
        """INSERT OR IGNORE INTO jobs
           (id, internal_job_id, title, department_id, location_raw,
            absolute_url, requisition_id, first_published, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            job["id"],
            job.get("internal_job_id"),
            job["title"],
            dept["id"],
            loc_raw,
            job.get("absolute_url"),
            job.get("requisition_id"),
            job.get("first_published"),
            today,
            today,
        ),
    )

    # Insert parsed locations
    for loc in parse_locations(loc_raw):
        conn.execute(
            "INSERT OR IGNORE INTO job_locations (job_id, location_name) VALUES (?, ?)",
            (job["id"], loc),
        )

    # Insert department join
    if dept["id"]:
        conn.execute(
            "INSERT OR IGNORE INTO job_departments (job_id, department_id) VALUES (?, ?)",
            (job["id"], dept["id"]),
        )

    # Insert office joins
    for office in job.get("offices", []):
        conn.execute(
            "INSERT OR IGNORE INTO job_offices (job_id, office_id) VALUES (?, ?)",
            (job["id"], office["id"]),
        )
