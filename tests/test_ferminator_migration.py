from __future__ import annotations

from pathlib import Path

MIGRATIONS = Path("supabase/migrations")


def migration_sql() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS.glob("*.sql"))
    )


def test_migration_enables_rls_on_every_private_table() -> None:
    sql = migration_sql().casefold()
    tables = [
        "profiles",
        "job_history",
        "company_watchlist",
        "companies",
        "ats_boards",
        "ingestion_runs",
        "jobs",
        "job_revisions",
        "job_locations",
        "job_matches",
        "job_actions",
        "action_events",
        "saved_searches",
        "notifications",
    ]

    for table in tables:
        assert f"alter table public.{table} enable row level security" in sql


def test_migration_uses_indexes_for_search_and_active_jobs() -> None:
    sql = migration_sql().casefold()

    assert "jobs_title_trgm_idx" in sql
    assert "job_revisions_search_idx" in sql
    assert "where active" in sql
