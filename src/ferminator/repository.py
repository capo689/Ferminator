"""Postgres persistence for profiles and normalized ATS ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ferminator.domain import BoardRef, NormalizedJob
from ferminator.ingestion import IngestionResult, LifecyclePlan
from ferminator.matching import MatchResult
from ferminator.profiles import CareerProfile


class PostgresRepository:
    """Small explicit SQL repository; service-role credentials stay server-side."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 5):
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with self.pool.connection() as connection:
            yield connection

    def sync_profile(self, profile: CareerProfile, email: str | None = None) -> str:
        compiled = profile.model_dump(
            mode="json",
            exclude={"markdown_body", "source_path", "source_hash"},
        )
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                insert into public.profiles (
                  slug, display_name, email, source_path, source_hash,
                  profile_version, scan_interval_hours, scan_enabled, compiled_profile
                )
                values (%s, %s, %s, %s, %s, 1, %s, %s, %s)
                on conflict (slug) do update set
                  display_name = excluded.display_name,
                  email = coalesce(excluded.email, profiles.email),
                  source_path = excluded.source_path,
                  profile_version = case
                    when profiles.source_hash <> excluded.source_hash
                    then profiles.profile_version + 1
                    else profiles.profile_version
                  end,
                  source_hash = excluded.source_hash,
                  scan_interval_hours = excluded.scan_interval_hours,
                  scan_enabled = excluded.scan_enabled,
                  compiled_profile = excluded.compiled_profile,
                  updated_at = now()
                returning id
                """,
                (
                    profile.profile.slug,
                    profile.profile.display_name,
                    email,
                    str(profile.source_path),
                    profile.source_hash,
                    profile.search.scan_interval_hours,
                    profile.search.enabled,
                    json.dumps(compiled),
                ),
            ).fetchone()
        return str(row["id"])

    def active_jobs(self) -> list[tuple[str, str, NormalizedJob]]:
        """Return job and revision identities with their normalized payload."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.id as job_id, r.id as revision_id, r.normalized_payload
                from public.jobs j
                join public.job_revisions r on r.id = j.current_revision_id
                where j.active
                order by j.first_seen_at desc
                """
            ).fetchall()
        return [
            (
                str(row["job_id"]),
                str(row["revision_id"]),
                NormalizedJob.model_validate(row["normalized_payload"]),
            )
            for row in rows
        ]

    def store_match(
        self,
        *,
        profile_id: str,
        profile_version: int,
        job_id: str,
        revision_id: str,
        match: MatchResult,
    ) -> None:
        with self.connection() as conn, conn.transaction():
            conn.execute(
                """
                insert into public.job_matches (
                  profile_id, job_id, job_revision_id, profile_version,
                  eligible, score, component_scores, matched_evidence,
                  concerns, explanation
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (profile_id, job_id, profile_version, job_revision_id)
                do update set
                  eligible = excluded.eligible,
                  score = excluded.score,
                  component_scores = excluded.component_scores,
                  matched_evidence = excluded.matched_evidence,
                  concerns = excluded.concerns,
                  explanation = excluded.explanation,
                  updated_at = now()
                """,
                (
                    profile_id,
                    job_id,
                    revision_id,
                    profile_version,
                    match.eligible,
                    match.score,
                    json.dumps(match.component_scores),
                    json.dumps(match.matched_evidence),
                    json.dumps(match.concerns),
                    match.explanation,
                ),
            )

    def profile_version(self, profile_id: str) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "select profile_version from public.profiles where id = %s",
                (profile_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Profile not found")
        return int(row["profile_version"])

    def top_matches(self, profile_id: str, *, limit: int = 10) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.title, j.company_name, j.job_url, j.apply_url,
                       j.first_seen_at, m.score, m.matched_evidence, m.concerns
                from public.job_matches m
                join public.jobs j on j.id = m.job_id
                where m.profile_id = %s and m.eligible and j.active
                  and m.profile_version = (
                    select profile_version from public.profiles where id = %s
                  )
                order by m.score desc, j.first_seen_at desc
                limit %s
                """,
                (profile_id, profile_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_notification(
        self,
        *,
        profile_id: str,
        idempotency_key: str,
        subject: str,
        payload: dict,
    ) -> str | None:
        """Atomically claim a notification; None means it was already created."""
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                insert into public.notifications (
                  profile_id, channel, notification_type, idempotency_key,
                  status, subject, payload, scheduled_for
                )
                values (%s, 'email', 'daily_digest', %s, 'sending', %s, %s, now())
                on conflict (idempotency_key) do nothing
                returning id
                """,
                (profile_id, idempotency_key, subject, json.dumps(payload)),
            ).fetchone()
        return str(row["id"]) if row else None

    def finish_notification(
        self,
        notification_id: str,
        *,
        sent: bool,
        error_code: str | None = None,
    ) -> None:
        with self.connection() as conn, conn.transaction():
            conn.execute(
                """
                update public.notifications
                set status = %s, sent_at = case when %s then now() else sent_at end,
                    attempt_count = attempt_count + 1,
                    last_error_code = %s, updated_at = now()
                where id = %s
                """,
                ("sent" if sent else "failed", sent, error_code, notification_id),
            )

    def _ensure_board(self, conn: Connection, board: BoardRef) -> str:
        company = conn.execute(
            """
            insert into public.companies (slug, name, website_url, career_url)
            values (%s, %s, null, %s)
            on conflict (slug) do update set
              name = excluded.name,
              career_url = excluded.career_url,
              updated_at = now()
            returning id
            """,
            (board.company_slug, board.company_name, str(board.source_url)),
        ).fetchone()
        row = conn.execute(
            """
            insert into public.ats_boards (
              company_id, provider, board_key, region, source_url
            )
            values (%s, %s, %s, %s, %s)
            on conflict (provider, board_key, region) do update set
              company_id = excluded.company_id,
              source_url = excluded.source_url,
              updated_at = now()
            returning id
            """,
            (
                company["id"],
                board.provider.value,
                board.board_key,
                board.region,
                str(board.source_url),
            ),
        ).fetchone()
        return str(row["id"])

    def active_source_ids(self, board: BoardRef) -> set[str]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.source_job_id
                from public.jobs j
                join public.ats_boards b on b.id = j.ats_board_id
                where b.provider = %s and b.board_key = %s and b.region = %s
                  and j.active
                """,
                (board.provider.value, board.board_key, board.region),
            ).fetchall()
        return {row["source_job_id"] for row in rows}

    def known_source_ids(self, board: BoardRef) -> set[str]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.source_job_id
                from public.jobs j
                join public.ats_boards b on b.id = j.ats_board_id
                where b.provider = %s and b.board_key = %s and b.region = %s
                """,
                (board.provider.value, board.board_key, board.region),
            ).fetchall()
        return {row["source_job_id"] for row in rows}

    def apply_ingestion(
        self,
        board: BoardRef,
        jobs: list[NormalizedJob],
        plan: LifecyclePlan,
        idempotency_key: str,
    ) -> IngestionResult:
        started = datetime.now(UTC)
        updated_count = 0
        with self.connection() as conn, conn.transaction():
            board_id = self._ensure_board(conn, board)
            existing_run = conn.execute(
                """
                select id, status from public.ingestion_runs
                where idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchone()
            if existing_run and existing_run["status"] == "succeeded":
                return IngestionResult(
                    board=board,
                    fetched=len(jobs),
                    added=0,
                    updated=0,
                    removed=0,
                    reactivated=0,
                    run_id=str(existing_run["id"]),
                )
            run = conn.execute(
                """
                insert into public.ingestion_runs (
                  board_id, provider, idempotency_key, status, started_at
                )
                values (%s, %s, %s, 'running', %s)
                on conflict (idempotency_key) do update set
                  status = 'running',
                  started_at = excluded.started_at,
                  finished_at = null,
                  error_code = null,
                  error_message = null
                returning id
                """,
                (board_id, board.provider.value, idempotency_key, started),
            ).fetchone()

            for job in jobs:
                current = conn.execute(
                    "select content_hash from public.job_revisions r "
                    "join public.jobs j on j.current_revision_id = r.id "
                    "where j.source_key = %s",
                    (job.source_key,),
                ).fetchone()
                if current and current["content_hash"] != job.content_hash:
                    updated_count += 1

                job_row = conn.execute(
                    """
                    insert into public.jobs (
                      ats_board_id, source_job_id, source_key, company_name, title,
                      department, team, employment_type, seniority, workplace_type,
                      salary_min, salary_max, salary_currency, salary_interval,
                      job_url, apply_url, published_at, source_updated_at,
                      first_seen_at, last_seen_at, active, removed_at
                    )
                    values (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s, %s, now(), now(), true, null
                    )
                    on conflict (source_key) do update set
                      ats_board_id = excluded.ats_board_id,
                      company_name = excluded.company_name,
                      title = excluded.title,
                      department = excluded.department,
                      team = excluded.team,
                      employment_type = excluded.employment_type,
                      seniority = excluded.seniority,
                      workplace_type = excluded.workplace_type,
                      salary_min = excluded.salary_min,
                      salary_max = excluded.salary_max,
                      salary_currency = excluded.salary_currency,
                      salary_interval = excluded.salary_interval,
                      job_url = excluded.job_url,
                      apply_url = excluded.apply_url,
                      published_at = coalesce(excluded.published_at, jobs.published_at),
                      source_updated_at = excluded.source_updated_at,
                      last_seen_at = now(),
                      active = true,
                      removed_at = null,
                      updated_at = now()
                    returning id
                    """,
                    (
                        board_id,
                        job.source_job_id,
                        job.source_key,
                        job.company_name,
                        job.title,
                        job.department,
                        job.team,
                        job.employment_type,
                        job.seniority,
                        job.workplace_type.value,
                        job.compensation.minimum if job.compensation else None,
                        job.compensation.maximum if job.compensation else None,
                        job.compensation.currency if job.compensation else None,
                        job.compensation.interval if job.compensation else None,
                        str(job.job_url),
                        str(job.apply_url) if job.apply_url else None,
                        job.published_at,
                        job.source_updated_at,
                    ),
                ).fetchone()
                revision = conn.execute(
                    """
                    insert into public.job_revisions (
                      job_id, content_hash, description_text, description_html,
                      search_document, normalized_payload
                    )
                    values (%s, %s, %s, %s, %s, %s)
                    on conflict (job_id, content_hash) do update set
                      observed_at = job_revisions.observed_at
                    returning id
                    """,
                    (
                        job_row["id"],
                        job.content_hash,
                        job.description_text,
                        job.description_html,
                        job.search_document,
                        json.dumps(job.model_dump(mode="json")),
                    ),
                ).fetchone()
                conn.execute(
                    "update public.jobs set current_revision_id = %s where id = %s",
                    (revision["id"], job_row["id"]),
                )
                conn.execute(
                    "delete from public.job_locations where job_id = %s",
                    (job_row["id"],),
                )
                for location in job.locations:
                    conn.execute(
                        """
                        insert into public.job_locations (
                          job_id, label, city, region, country, country_code,
                          is_primary, is_remote, normalized_key
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            job_row["id"],
                            location.label,
                            location.city,
                            location.region,
                            location.country,
                            location.country_code,
                            location.is_primary,
                            location.is_remote,
                            location.normalized_key,
                        ),
                    )

            if plan.removed:
                conn.execute(
                    """
                    update public.jobs
                    set active = false, removed_at = now(), updated_at = now()
                    where ats_board_id = %s and source_job_id = any(%s)
                    """,
                    (board_id, list(plan.removed)),
                )

            finished = datetime.now(UTC)
            duration_ms = int((finished - started).total_seconds() * 1000)
            conn.execute(
                """
                update public.ingestion_runs
                set status = 'succeeded', finished_at = %s, duration_ms = %s,
                    fetched_count = %s, inserted_count = %s, updated_count = %s,
                    removed_count = %s
                where id = %s
                """,
                (
                    finished,
                    duration_ms,
                    len(jobs),
                    len(plan.added),
                    updated_count,
                    len(plan.removed),
                    run["id"],
                ),
            )
            conn.execute(
                """
                update public.ats_boards
                set validation_status = 'healthy', consecutive_failures = 0,
                    last_validated_at = now(), last_success_at = now(),
                    last_error_code = null, updated_at = now()
                where id = %s
                """,
                (board_id,),
            )

        return IngestionResult(
            board=board,
            fetched=len(jobs),
            added=len(plan.added),
            updated=updated_count,
            removed=len(plan.removed),
            reactivated=len(plan.reactivated),
            run_id=str(run["id"]),
        )
