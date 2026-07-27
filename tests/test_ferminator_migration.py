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


def test_alpha_hardening_migration_adds_observability_and_feedback() -> None:
    sql = migration_sql().casefold()

    assert "create table public.scan_runs" in sql
    assert "create table public.match_feedback" in sql
    assert "alter table public.scan_runs enable row level security" in sql
    assert "alter table public.match_feedback enable row level security" in sql
    assert "revoke all on public.scan_runs from anon, authenticated" in sql


def test_match_feedback_is_reversible_and_supports_duplicates() -> None:
    sql = migration_sql().casefold()

    assert "'duplicate'" in sql
    assert "create table public.match_feedback_events" in sql
    assert "alter table public.match_feedback_events enable row level security" in sql
    assert "match_feedback_profile_job_key unique (profile_id, job_id)" in sql


def test_company_registry_is_not_available_through_client_roles() -> None:
    sql = migration_sql().casefold()

    assert (
        'drop policy if exists "authenticated_read_companies" '
        "on public.companies"
    ) in sql
    assert (
        'drop policy if exists "authenticated_read_boards" '
        "on public.ats_boards"
    ) in sql
    assert (
        "revoke all privileges on table public.companies "
        "from anon, authenticated"
    ) in sql
    assert (
        "revoke all privileges on table public.ats_boards "
        "from anon, authenticated"
    ) in sql


def test_wrong_feedback_has_structured_reason_and_audit_evidence() -> None:
    sql = migration_sql().casefold()

    assert "add column wrong_reason_code text" in sql
    assert "match_feedback_wrong_reason_code_check" in sql
    assert "match_feedback_events_wrong_reason_code_check" in sql
    assert "match_feedback_profile_wrong_reason_idx" in sql


def test_multi_user_beta_uses_native_identity_and_private_control_plane() -> None:
    sql = migration_sql().casefold()

    assert "auth_user_id uuid not null unique references auth.users(id)" in sql
    assert "accounts_single_sysadmin_idx" in sql
    assert "accounts_enforce_beta_user_limit" in sql
    assert "matching_run_queue_one_active_per_account_idx" in sql
    assert "accounts_deny_direct_client_access" in sql
    assert "admin_audit_events_deny_direct_client_access" in sql
    assert "auth0" not in sql
