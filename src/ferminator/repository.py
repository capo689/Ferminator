"""Postgres persistence for profiles and normalized ATS ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ferminator.domain import BoardRef, NormalizedJob
from ferminator.ingestion import IngestionResult, LifecyclePlan
from ferminator.ledger import ParsedLedger, job_fingerprint, normalize_job_part
from ferminator.matching import MatchResult
from ferminator.profiles import CareerProfile

if TYPE_CHECKING:
    from ferminator.registry import CompanyRegistry


class ConcurrentScoringError(RuntimeError):
    """Raised when another scoring pass already owns the profile lock."""


class ConcurrentScanError(RuntimeError):
    """Raised when another full scan is already active."""


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

    @contextmanager
    def scan_lock(self) -> Iterator[None]:
        """Hold a session advisory lock for the complete ingest-and-score pass."""
        with self.connection() as conn:
            row = conn.execute(
                "select pg_try_advisory_lock(hashtextextended(%s, 0)) as acquired",
                ("ferminator:full-scan",),
            ).fetchone()
            if not row["acquired"]:
                raise ConcurrentScanError("Another Ferminator scan is already running")
            try:
                yield
            finally:
                conn.execute(
                    "select pg_advisory_unlock(hashtextextended(%s, 0))",
                    ("ferminator:full-scan",),
                )

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

    def store_matches(
        self,
        *,
        profile_id: str,
        profile_version: int,
        matches: list[tuple[str, str, MatchResult]],
    ) -> None:
        """Upsert a complete profile scoring pass in one database transaction."""
        if not matches:
            return
        parameters = [
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
            )
            for job_id, revision_id, match in matches
        ]
        with self.connection() as conn, conn.transaction():
            conn.execute("set local lock_timeout = '5s'")
            conn.execute("set local statement_timeout = '60s'")
            lock = conn.execute(
                "select pg_try_advisory_xact_lock(hashtextextended(%s, 0)) as acquired",
                (f"ferminator:score:{profile_id}",),
            ).fetchone()
            if not lock["acquired"]:
                raise ConcurrentScoringError(
                    "Another scoring pass is already running for this profile"
                )
            with conn.cursor() as cursor:
                cursor.executemany(
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
                    where (
                      job_matches.eligible,
                      job_matches.score,
                      job_matches.component_scores,
                      job_matches.matched_evidence,
                      job_matches.concerns,
                      job_matches.explanation
                    ) is distinct from (
                      excluded.eligible,
                      excluded.score,
                      excluded.component_scores,
                      excluded.matched_evidence,
                      excluded.concerns,
                      excluded.explanation
                    )
                    """,
                    parameters,
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

    def top_matches(
        self,
        profile_id: str,
        *,
        minimum_score: float = 0,
        limit: int = 10,
    ) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.title, j.company_name, j.job_url, j.apply_url,
                       j.first_seen_at, m.score, m.matched_evidence, m.concerns
                from public.job_matches m
                join public.jobs j on j.id = m.job_id
                where m.profile_id = %s and m.eligible and j.active
                  and m.score >= %s
                  and not exists (
                    select 1 from public.job_history h
                    where h.profile_id = m.profile_id
                      and (
                        h.source_job_key = j.source_key
                        or (
                        h.fingerprint = public.normalize_job_part(j.company_name)
                          || '::' || public.normalize_job_part(j.title)
                          and (h.permanent or h.suppress_until > now())
                        )
                      )
                  )
                  and m.profile_version = (
                    select profile_version from public.profiles where id = %s
                  )
                order by m.score desc, j.first_seen_at desc
                limit %s
                """,
                (profile_id, minimum_score, profile_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def web_matches(
        self,
        profile_slug: str,
        *,
        minimum_score: float = 0,
        limit: int = 500,
        include_suppressed: bool = False,
    ) -> list[dict]:
        """Return current, eligible matches shaped for the server-rendered UI."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.id, j.title, j.company_name, c.slug as company_slug,
                       j.department, j.workplace_type, j.salary_min, j.salary_max,
                       j.salary_currency, j.job_url, j.apply_url, j.published_at,
                       j.first_seen_at, b.provider, m.score, m.component_scores,
                       m.matched_evidence, m.concerns, m.explanation,
                       coalesce(l.label, 'Location unspecified') as location
                from public.profiles p
                join public.job_matches m on m.profile_id = p.id
                join public.jobs j on j.id = m.job_id and j.active
                join public.ats_boards b on b.id = j.ats_board_id
                join public.companies c on c.id = b.company_id
                left join lateral (
                  select label from public.job_locations
                  where job_id = j.id
                  order by (
                    country_code = 'US'
                    or label ~* 'United States'
                    or label ~* '(^|[^A-Za-z])(US|USA)([^A-Za-z]|$)'
                  ) desc nulls last, is_primary desc, is_remote desc, label
                  limit 1
                ) l on true
                where p.slug = %s and m.eligible and m.score >= %s
                  and m.profile_version = p.profile_version
                  and m.job_revision_id = j.current_revision_id
                  and (%s or not exists (
                    select 1 from public.job_history h
                    where h.profile_id = p.id
                      and (
                        h.source_job_key = j.source_key
                        or (
                          h.fingerprint = public.normalize_job_part(j.company_name)
                            || '::' || public.normalize_job_part(j.title)
                          and (h.permanent or h.suppress_until > now())
                        )
                      )
                  ))
                order by m.score desc, j.first_seen_at desc
                limit %s
                """,
                (profile_slug, minimum_score, include_suppressed, limit),
            ).fetchall()
        now = datetime.now(UTC)
        result = []
        for row in rows:
            item = dict(row)
            published = item["published_at"] or item["first_seen_at"]
            age_hours = max(0, int((now - published).total_seconds() / 3600))
            salary = None
            if item["salary_min"] is not None:
                upper = item["salary_max"] or item["salary_min"]
                symbol = (
                    "$"
                    if item["salary_currency"] in {None, "USD"}
                    else item["salary_currency"]
                )
                lower_label = f"{symbol}{float(item['salary_min']) / 1000:,.0f}K"
                upper_label = f"{symbol}{float(upper) / 1000:,.0f}K"
                salary = f"{lower_label}–{upper_label}"
            result.append(
                {
                    **item,
                    "id": str(item["id"]),
                    "company": item["company_name"],
                    "company_initial": item["company_name"][0],
                    "workplace": item["workplace_type"],
                    "compensation": salary,
                    "score": float(item["score"]),
                    "evidence": item["matched_evidence"],
                    "freshness": (
                        f"{age_hours}h ago"
                        if age_hours < 48
                        else f"{age_hours // 24}d ago"
                    ),
                    "apply_url": item["apply_url"] or item["job_url"],
                }
            )
        return result

    def pipeline(self, profile_slug: str) -> dict[str, list[dict]]:
        matches = {
            item["id"]: item
            for item in self.web_matches(profile_slug, include_suppressed=True)
        }
        stage_names = ("Considering", "Preparing", "Applied", "Interviewing", "Offer")
        stages = {name: [] for name in stage_names}
        with self.connection() as conn:
            rows = conn.execute(
                """
                select a.job_id, a.state, a.notes, a.follow_up_at
                from public.job_actions a
                join public.profiles p on p.id = a.profile_id
                where p.slug = %s and a.state not in ('closed', 'dismissed')
                order by a.updated_at desc
                """,
                (profile_slug,),
            ).fetchall()
        for row in rows:
            job = matches.get(str(row["job_id"]))
            if job:
                job = {**job, "task": row["notes"], "due": row["follow_up_at"]}
                stages[row["state"].title()].append(job)
        return stages

    def company_stats(self, profile_slug: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.company_name as name, count(*) filter (where m.eligible) as relevant,
                       count(*) filter (
                         where m.eligible and j.first_seen_at >= now() - interval '24 hours'
                       ) as new
                from public.profiles p
                join public.job_matches m on m.profile_id = p.id
                  and m.profile_version = p.profile_version
                join public.jobs j on j.id = m.job_id and j.active
                  and j.current_revision_id = m.job_revision_id
                where p.slug = %s
                group by j.company_name
                order by relevant desc, name
                """,
                (profile_slug,),
            ).fetchall()
        return [
            {
                "name": row["name"],
                "initial": row["name"][0],
                "momentum": 0,
                "relevant": row["relevant"],
                "new": row["new"],
            }
            for row in rows
        ]

    def company_directory(self, profile_slug: str) -> list[dict]:
        """Return registered boards with source health and useful job counts."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select c.name, c.slug, c.priority, c.website_url,
                       b.provider, b.board_key, b.region, b.source_url,
                       b.validation_status, b.consecutive_failures,
                       b.last_validated_at, b.last_success_at, b.last_error_code,
                       count(distinct j.id) filter (where j.active) as active_jobs,
                       count(distinct j.id) filter (
                         where j.active and m.eligible
                       ) as relevant_jobs,
                       count(distinct j.id) filter (
                         where j.active and j.first_seen_at >= now() - interval '24 hours'
                       ) as new_jobs
                from public.companies c
                join public.ats_boards b on b.company_id = c.id
                left join public.jobs j on j.ats_board_id = b.id
                left join public.profiles p on p.slug = %s
                left join public.job_matches m on m.profile_id = p.id
                  and m.job_id = j.id
                  and m.profile_version = p.profile_version
                  and m.job_revision_id = j.current_revision_id
                where c.enabled and b.enabled and b.validation_status <> 'failed'
                group by c.id, b.id
                order by c.priority desc, c.name, b.provider
                """,
                (profile_slug,),
            ).fetchall()
        return [
            {
                **dict(row),
                "initial": row["name"][0],
                "healthy": row["validation_status"] == "healthy",
                "active_jobs": int(row["active_jobs"]),
                "relevant_jobs": int(row["relevant_jobs"]),
                "new_jobs": int(row["new_jobs"]),
            }
            for row in rows
        ]

    def set_action(self, profile_slug: str, job_id: str, state: str) -> None:
        allowed = {"considering", "preparing", "applied", "interviewing", "offer", "dismissed"}
        if state not in allowed:
            raise ValueError("Unsupported pipeline state")
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                insert into public.job_actions (profile_id, job_id, state)
                select p.id, j.id, %s::public.pipeline_state
                from public.profiles p, public.jobs j
                where p.slug = %s and j.id = %s and j.active
                on conflict (profile_id, job_id) do update
                  set state = excluded.state, updated_at = now()
                returning id, profile_id, job_id
                """,
                (state, profile_slug, job_id),
            ).fetchone()
            if row is None:
                raise LookupError("Profile or job not found")
            if state == "applied":
                job = conn.execute(
                    """
                    select company_name, title, source_key
                    from public.jobs where id = %s
                    """,
                    (row["job_id"],),
                ).fetchone()
                fingerprint = job_fingerprint(job["company_name"], job["title"])
                conn.execute(
                    """
                    update public.job_actions
                    set applied_at = coalesce(applied_at, now())
                    where id = %s
                    """,
                    (row["id"],),
                )
                conn.execute(
                    """
                    insert into public.job_history (
                      profile_id, job_id, company_name, title, normalized_company,
                      normalized_title, fingerprint, category, status, source,
                      source_job_key, first_recorded_at, applied_at, suppress_until
                    )
                    values (
                      %s, %s, %s, %s, %s, %s, %s, 'Applied', 'Applied',
                      'dashboard', %s, now(), now(), now() + interval '183 days'
                    )
                    on conflict (profile_id, fingerprint) do update set
                      job_id = excluded.job_id,
                      category = 'Applied',
                      status = 'Applied',
                      source_job_key = excluded.source_job_key,
                      applied_at = coalesce(job_history.applied_at, excluded.applied_at),
                      suppress_until = greatest(
                        job_history.suppress_until, excluded.suppress_until
                      ),
                      updated_at = now()
                    """,
                    (
                        row["profile_id"],
                        row["job_id"],
                        job["company_name"],
                        job["title"],
                        normalize_job_part(job["company_name"]),
                        normalize_job_part(job["title"]),
                        fingerprint,
                        job["source_key"],
                    ),
                )
            conn.execute(
                """
                insert into public.action_events (
                  profile_id, job_id, action_id, event_type, to_state
                ) values (%s, %s, %s, 'state_changed', %s::public.pipeline_state)
                """,
                (row["profile_id"], row["job_id"], row["id"], state),
            )

    def set_match_feedback(
        self,
        profile_slug: str,
        job_id: str,
        verdict: str,
        *,
        reason: str | None = None,
    ) -> None:
        """Capture a durable quality verdict against the exact scored revision."""
        if verdict not in {"great", "maybe", "wrong"}:
            raise ValueError("Unsupported match verdict")
        clean_reason = reason.strip()[:500] if reason and reason.strip() else None
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                insert into public.match_feedback (
                  profile_id, job_id, job_revision_id, profile_version, verdict,
                  reason, score_at_feedback, component_scores
                )
                select p.id, j.id, m.job_revision_id, m.profile_version, %s, %s,
                       m.score, m.component_scores
                from public.profiles p
                join public.jobs j on j.id = %s
                join public.job_matches m on m.profile_id = p.id
                  and m.job_id = j.id
                  and m.profile_version = p.profile_version
                  and m.job_revision_id = j.current_revision_id
                where p.slug = %s
                on conflict (profile_id, job_id, profile_version, job_revision_id)
                do update set verdict = excluded.verdict, reason = excluded.reason,
                              score_at_feedback = excluded.score_at_feedback,
                              component_scores = excluded.component_scores,
                              updated_at = now()
                returning id
                """,
                (verdict, clean_reason, job_id, profile_slug),
            ).fetchone()
            if row is None:
                raise LookupError("Current profile match not found")

    def match_quality(self, profile_slug: str) -> dict:
        """Return transparent quality metrics from explicit human verdicts."""
        with self.connection() as conn:
            summary = conn.execute(
                """
                select count(*) as reviewed,
                       count(*) filter (where f.verdict = 'great') as great,
                       count(*) filter (where f.verdict = 'maybe') as maybe,
                       count(*) filter (where f.verdict = 'wrong') as wrong,
                       avg(f.score_at_feedback) filter (where f.verdict = 'great')
                         as great_average,
                       avg(f.score_at_feedback) filter (where f.verdict = 'wrong')
                         as wrong_average
                from public.match_feedback f
                join public.profiles p on p.id = f.profile_id
                where p.slug = %s
                """,
                (profile_slug,),
            ).fetchone()
            reasons = conn.execute(
                """
                select reason, count(*) as count
                from public.match_feedback f
                join public.profiles p on p.id = f.profile_id
                where p.slug = %s and f.verdict = 'wrong' and reason is not null
                group by reason
                order by count(*) desc, reason
                limit 8
                """,
                (profile_slug,),
            ).fetchall()
        reviewed = int(summary["reviewed"])
        useful = int(summary["great"]) + int(summary["maybe"])
        return {
            **dict(summary),
            "reviewed": reviewed,
            "useful_rate": round(100 * useful / reviewed, 1) if reviewed else None,
            "wrong_reasons": [dict(row) for row in reasons],
        }

    def source_health(self) -> dict:
        """Summarize source and full-scan health without exposing provider payloads."""
        with self.connection() as conn:
            boards = conn.execute(
                """
                select c.name as company, b.provider, b.board_key,
                       b.validation_status, b.consecutive_failures,
                       b.last_success_at, b.last_validated_at, b.last_error_code
                from public.ats_boards b
                join public.companies c on c.id = b.company_id
                where b.enabled
                order by b.consecutive_failures desc, c.name
                """
            ).fetchall()
            latest_scan = conn.execute(
                """
                select status, started_at, finished_at, board_count,
                       succeeded_count, failed_count, scored_job_count, error_codes
                from public.scan_runs
                order by started_at desc
                limit 1
                """
            ).fetchone()
        return {
            "latest_scan": dict(latest_scan) if latest_scan else None,
            "boards": [dict(row) for row in boards],
        }

    def start_scan(self, idempotency_key: str, board_count: int) -> str:
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                insert into public.scan_runs (idempotency_key, status, board_count)
                values (%s, 'running', %s)
                on conflict (idempotency_key) do update set
                  status = case
                    when scan_runs.status = 'succeeded' then scan_runs.status
                    else 'running'::public.run_status
                  end,
                  started_at = case
                    when scan_runs.status = 'succeeded' then scan_runs.started_at
                    else now()
                  end,
                  finished_at = case
                    when scan_runs.status = 'succeeded' then scan_runs.finished_at
                    else null
                  end
                returning id
                """,
                (idempotency_key, board_count),
            ).fetchone()
        return str(row["id"])

    def finish_scan(
        self,
        scan_id: str,
        *,
        succeeded: int,
        failed: int,
        scored_jobs: int,
        error_codes: list[str],
    ) -> None:
        with self.connection() as conn, conn.transaction():
            conn.execute(
                """
                update public.scan_runs
                set status = %s::public.run_status, finished_at = now(),
                    succeeded_count = %s, failed_count = %s,
                    scored_job_count = %s, error_codes = %s
                where id = %s and status = 'running'
                """,
                (
                    "failed" if failed else "succeeded",
                    succeeded,
                    failed,
                    scored_jobs,
                    json.dumps(sorted(set(error_codes))),
                    scan_id,
                ),
            )

    def import_ledger(self, profile_slug: str, ledger: ParsedLedger) -> tuple[int, int]:
        """Idempotently import suppression history and advisory company warnings."""
        with self.connection() as conn, conn.transaction():
            profile = conn.execute(
                "select id from public.profiles where slug = %s",
                (profile_slug,),
            ).fetchone()
            if profile is None:
                raise LookupError("Profile not found")
            for entry in ledger.entries:
                conn.execute(
                    """
                    insert into public.job_history (
                      profile_id, company_name, title, normalized_company,
                      normalized_title, fingerprint, category, status, source,
                      first_recorded_at, suppress_until, permanent, applied_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, 'master-ledger',
                            %s, %s, %s, case when %s = 'applied' then %s end)
                    on conflict (profile_id, fingerprint) do update set
                      category = excluded.category,
                      status = excluded.status,
                      suppress_until = case
                        when job_history.permanent then null
                        else greatest(job_history.suppress_until, excluded.suppress_until)
                      end,
                      permanent = job_history.permanent or excluded.permanent,
                      updated_at = now()
                    """,
                    (
                        profile["id"], entry.company, entry.title,
                        normalize_job_part(entry.company), normalize_job_part(entry.title),
                        entry.fingerprint, entry.category, entry.status,
                        entry.first_recorded_at, entry.suppress_until, entry.permanent,
                        entry.category.casefold(), entry.first_recorded_at,
                    ),
                )
            for watch in ledger.company_watchlist:
                conn.execute(
                    """
                    insert into public.company_watchlist (
                      profile_id, company_name, normalized_company
                    ) values (%s, %s, %s)
                    on conflict (profile_id, normalized_company) do update set
                      company_name = excluded.company_name, updated_at = now()
                    """,
                    (profile["id"], watch.company, watch.normalized_company),
                )
        return len(ledger.entries), len(ledger.company_watchlist)

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

    def sync_registry(self, registry: CompanyRegistry) -> tuple[int, int]:
        """Idempotently mirror the Git-controlled registry into the live directory."""
        company_count = 0
        board_count = 0
        with self.connection() as conn, conn.transaction():
            for company in registry.companies:
                company_row = conn.execute(
                    """
                    insert into public.companies (
                      slug, name, website_url, career_url, enabled, priority, metadata
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (slug) do update set
                      name = excluded.name,
                      website_url = excluded.website_url,
                      career_url = excluded.career_url,
                      enabled = excluded.enabled,
                      priority = excluded.priority,
                      metadata = companies.metadata || excluded.metadata,
                      updated_at = now()
                    returning id
                    """,
                    (
                        company.slug,
                        company.name,
                        str(company.website_url) if company.website_url else None,
                        str(company.career_url) if company.career_url else None,
                        company.enabled,
                        company.priority,
                        json.dumps({"registry_schema_version": registry.schema_version}),
                    ),
                ).fetchone()
                company_count += 1
                for board in company.boards:
                    conn.execute(
                        """
                        insert into public.ats_boards (
                          company_id, provider, board_key, region, source_url,
                          enabled, metadata
                        )
                        values (%s, %s, %s, %s, %s, %s, %s)
                        on conflict (provider, board_key, region) do update set
                          company_id = excluded.company_id,
                          source_url = excluded.source_url,
                          enabled = excluded.enabled,
                          metadata = ats_boards.metadata || excluded.metadata,
                          updated_at = now()
                        """,
                        (
                            company_row["id"],
                            board.provider.value,
                            board.board_key,
                            board.region,
                            str(board.source_url),
                            company.enabled and board.enabled,
                            json.dumps({"managed_by": "config/companies.yaml"}),
                        ),
                    )
                    board_count += 1
        return company_count, board_count

    def record_ingestion_failure(
        self,
        board: BoardRef,
        *,
        idempotency_key: str,
        error_code: str,
    ) -> None:
        """Record failures that happen before a provider payload can be ingested."""
        safe_code = error_code[:120]
        with self.connection() as conn, conn.transaction():
            board_id = self._ensure_board(conn, board)
            conn.execute(
                """
                insert into public.ingestion_runs (
                  board_id, provider, idempotency_key, status, started_at,
                  finished_at, failed_count, error_code, error_message
                )
                values (%s, %s, %s, 'failed', now(), now(), 1, %s,
                        'Provider fetch or validation failed')
                on conflict (idempotency_key) do update set
                  status = 'failed', finished_at = now(), failed_count = 1,
                  error_code = excluded.error_code,
                  error_message = excluded.error_message
                """,
                (board_id, board.provider.value, idempotency_key, safe_code),
            )
            conn.execute(
                """
                update public.ats_boards
                set validation_status = case
                      when consecutive_failures + 1 >= 3 then 'failed'
                      else 'degraded'
                    end,
                    consecutive_failures = consecutive_failures + 1,
                    last_validated_at = now(), last_error_code = %s,
                    updated_at = now()
                where id = %s
                """,
                (safe_code, board_id),
            )

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
                        on conflict (job_id, normalized_key) do update set
                          label = excluded.label,
                          city = coalesce(excluded.city, job_locations.city),
                          region = coalesce(excluded.region, job_locations.region),
                          country = coalesce(excluded.country, job_locations.country),
                          country_code = coalesce(
                            excluded.country_code,
                            job_locations.country_code
                          ),
                          is_primary = job_locations.is_primary or excluded.is_primary,
                          is_remote = job_locations.is_remote or excluded.is_remote
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
