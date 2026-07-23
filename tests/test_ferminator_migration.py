from __future__ import annotations

from pathlib import Path

MIGRATION = Path("supabase/migrations/20260723052001_initial_ferminator_schema.sql")


def test_migration_enables_rls_on_every_private_table() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").casefold()
    tables = [
        "profiles",
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
    sql = MIGRATION.read_text(encoding="utf-8").casefold()

    assert "jobs_title_trgm_idx" in sql
    assert "job_revisions_search_idx" in sql
    assert "where active" in sql
