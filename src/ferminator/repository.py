"""Postgres persistence for profiles and normalized ATS ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ferminator.domain import ATSProvider, BoardRef, NormalizedJob
from ferminator.feedback import WRONG_REASON_CODES
from ferminator.ingestion import IngestionResult, LifecyclePlan
from ferminator.ledger import (
    ParsedLedger,
    compare_prior_job_titles,
    job_fingerprint,
    normalize_job_part,
)
from ferminator.matching import MatchResult
from ferminator.profiles import CareerProfile, load_compiled_profile, load_profile

# Discover keeps a job visible until it is dealt with, but carrying every job
# that was ever eligible pulled ~2,300 rows through the per-row lateral joins
# and made the page take over a minute. Anything under this floor was never
# going to clear the role thresholds downstream anyway.
STICKY_SCORE_FLOOR = 40

if TYPE_CHECKING:
    from ferminator.registry import CompanyRegistry


class ConcurrentScoringError(RuntimeError):
    """Raised when another scoring pass already owns the profile lock."""


class ConcurrentScanError(RuntimeError):
    """Raised when another full scan is already active."""


@dataclass(frozen=True)
class AccountContext:
    id: str
    auth_user_id: str
    username: str
    email: str
    role: str
    status: str
    profile_id: str | None
    profile_slug: str | None


def jobs_requiring_upsert(
    jobs: list[NormalizedJob],
    current_hashes: dict[str, str | None],
) -> tuple[list[NormalizedJob], int]:
    """Select new/materially changed jobs and count updates without DB round trips."""
    changed = [
        job for job in jobs if current_hashes.get(job.source_key) != job.content_hash
    ]
    updated = sum(job.source_key in current_hashes for job in changed)
    return changed, updated


class PostgresRepository:
    """Small explicit SQL repository; service-role credentials stay server-side."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 5):
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
            # A long-lived pool will eventually hold a connection the pooler has
            # dropped. Check on checkout so a dead socket is replaced rather
            # than handed to a request.
            check=ConnectionPool.check_connection,
        )

    def close(self) -> None:
        self.pool.close()

    def account_for_user(self, user_id: str) -> AccountContext | None:
        """Resolve a browser identity to its server-managed account and profile."""
        with self.connection() as conn:
            row = conn.execute(
                """
                select a.id, a.auth_user_id, a.username, a.email, a.role, a.status,
                       a.profile_id, p.slug as profile_slug
                from public.accounts a
                left join public.profiles p on p.id = a.profile_id
                where a.auth_user_id = %s
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        values = {
            key: str(value) if key in {"id", "auth_user_id", "profile_id"} and value else value
            for key, value in row.items()
        }
        return AccountContext(**values)

    def login_email_for_username(self, username: str) -> str | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                select email
                from public.accounts
                where (lower(username) = lower(%s) or lower(email) = lower(%s))
                  and status = 'active'
                """,
                (username, username),
            ).fetchone()
        return str(row["email"]) if row else None

    def record_login(self, account_id: str) -> None:
        with self.connection() as conn, conn.transaction():
            conn.execute(
                """
                update public.accounts
                set last_login_at = now(), updated_at = now()
                where id = %s
                """,
                (account_id,),
            )

    def admin_accounts(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                select a.id, a.username, a.email, a.role, a.status, a.last_login_at,
                       a.created_at, p.slug as profile_slug, p.display_name,
                       s.timezone, s.run_times, s.enabled as schedule_enabled,
                       r.status as latest_run_status, r.requested_at as latest_run_at
                from public.accounts a
                left join public.profiles p on p.id = a.profile_id
                left join public.account_schedules s on s.account_id = a.id
                left join lateral (
                  select status, requested_at
                  from public.matching_run_queue q
                  where q.account_id = a.id
                  order by requested_at desc
                  limit 1
                ) r on true
                order by case when a.role = 'sysadmin' then 0 else 1 end,
                         lower(a.username)
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def provision_user_account(
        self,
        *,
        auth_user_id: str,
        username: str,
        email: str,
        profile: CareerProfile,
        onboarding_markdown: str,
        timezone: str,
        run_times: list[str],
        actor_account_id: str,
        request_id: str,
    ) -> str:
        compiled = profile.model_dump(
            mode="json",
            exclude={"markdown_body", "source_path", "source_hash"},
        )
        with self.connection() as conn, conn.transaction():
            profile_row = conn.execute(
                """
                insert into public.profiles (
                  auth_user_id, slug, display_name, email, source_path, source_hash,
                  profile_version, scan_interval_hours, scan_enabled, compiled_profile,
                  onboarding_markdown, onboarding_schema_version
                )
                values (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    auth_user_id,
                    profile.profile.slug,
                    profile.profile.display_name,
                    email,
                    f"db://profiles/{profile.profile.slug}/v1.md",
                    profile.source_hash,
                    profile.search.scan_interval_hours,
                    profile.search.enabled,
                    json.dumps(compiled),
                    onboarding_markdown,
                    profile.schema_version,
                ),
            ).fetchone()
            account = conn.execute(
                """
                insert into public.accounts (
                  auth_user_id, profile_id, username, email, role, status
                )
                values (%s, %s, %s, %s, 'user', 'active')
                returning id
                """,
                (auth_user_id, profile_row["id"], username, email),
            ).fetchone()
            conn.execute(
                """
                insert into public.account_schedules (account_id, timezone, run_times)
                values (%s, %s, %s::time[])
                """,
                (account["id"], timezone, run_times),
            )
            conn.execute(
                """
                insert into public.matching_run_queue (
                  account_id, requested_by, reason, status
                )
                values (%s, %s, 'onboarding', 'queued')
                """,
                (account["id"], actor_account_id),
            )
            conn.execute(
                """
                insert into public.admin_audit_events (
                  actor_account_id, target_account_id, action, request_id, after_state
                )
                values (%s, %s, 'account.provisioned', %s, %s)
                """,
                (
                    actor_account_id,
                    account["id"],
                    request_id,
                    json.dumps(
                        {
                            "username": username,
                            "email": email,
                            "profile_slug": profile.profile.slug,
                            "timezone": timezone,
                            "run_times": run_times,
                        }
                    ),
                ),
            )
        return str(account["id"])

    def claim_password_reset_token(self, token_hash: str) -> dict | None:
        """Atomically consume a single-use password-reset token.

        Returns the target account's ids, or None when the token is unknown,
        already used, or expired. The update and the read happen in one
        statement so a token cannot be redeemed twice concurrently.
        """
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                update public.password_reset_tokens t
                set used_at = now()
                from public.accounts a
                where t.account_id = a.id
                  and t.token_hash = %s
                  and t.used_at is null
                  and t.expires_at > now()
                returning a.id as account_id, a.auth_user_id, a.username
                """,
                (token_hash,),
            ).fetchone()
        return dict(row) if row else None

    def release_password_reset_token(self, token_hash: str) -> None:
        """Un-consume a token whose password update did not go through.

        Claiming before the Supabase call meant one failed attempt burned the
        link and the user had to ask for a new one.
        """
        with self.connection() as conn, conn.transaction():
            conn.execute(
                """
                update public.password_reset_tokens
                set used_at = null
                where token_hash = %s and used_at is not null
                """,
                (token_hash,),
            )

    @staticmethod
    def _hydrate_profile(row: Mapping[str, Any]) -> CareerProfile:
        """Rebuild a CareerProfile from a profiles row.

        Legacy rows predate database-hosted onboarding Markdown and still point
        at a file on disk. Anything provisioned through /admin stores its
        Markdown in the row itself, under a db:// source path.
        """
        if not row["onboarding_markdown"] and not str(row["source_path"]).startswith("db://"):
            return load_profile(row["source_path"])
        return load_compiled_profile(
            dict(row["compiled_profile"]),
            markdown_body=row["onboarding_markdown"] or "",
            source_path=row["source_path"],
            source_hash=row["source_hash"],
        )

    def profile_for_account(self, account_id: str) -> CareerProfile:
        with self.connection() as conn:
            row = conn.execute(
                """
                select p.compiled_profile, p.onboarding_markdown, p.source_path, p.source_hash
                from public.accounts a
                join public.profiles p on p.id = a.profile_id
                where a.id = %s and a.role = 'user' and a.status = 'active'
                """,
                (account_id,),
            ).fetchone()
        if not row:
            raise LookupError("No active profile is assigned to this account")
        return self._hydrate_profile(row)

    def scannable_profiles(self) -> list[tuple[str, CareerProfile]]:
        """Every profile the scanner should score, sourced from the database.

        The scanner used to enumerate profiles by globbing profiles/*.md, so an
        account provisioned through /admin -- whose Markdown lives in its row
        rather than on disk -- was never scored. Those users could sign in and
        would see an empty dashboard indefinitely, with no error raised.
        """
        with self.connection() as conn:
            rows = conn.execute(
                """
                select p.id, p.slug, p.compiled_profile, p.onboarding_markdown,
                       p.source_path, p.source_hash
                from public.profiles p
                join public.accounts a on a.profile_id = p.id
                where a.role = 'user' and a.status = 'active' and p.scan_enabled
                order by p.slug
                """
            ).fetchall()
        return [(str(row["id"]), self._hydrate_profile(row)) for row in rows]

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with self.pool.connection() as connection:
            yield connection

    @contextmanager
    def scan_lock(self, key: str = "full-scan") -> Iterator[None]:
        """Hold a session advisory lock for one ingest pass.

        The key is scoped so provider shards can run in parallel: a Greenhouse
        pull and a Workday pull touch different boards and must not block each
        other. A single global key meant the second shard raised
        ConcurrentScanError immediately.
        """
        lock_name = f"ferminator:{key}"
        with self.connection() as conn:
            row = conn.execute(
                "select pg_try_advisory_lock(hashtextextended(%s, 0)) as acquired",
                (lock_name,),
            ).fetchone()
            if not row["acquired"]:
                raise ConcurrentScanError(f"Another Ferminator scan is already running ({key})")
            try:
                yield
            finally:
                conn.execute(
                    "select pg_advisory_unlock(hashtextextended(%s, 0))",
                    (lock_name,),
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

    def expire_unseen_jobs(self, *, stale_after_days: int = 3) -> list[dict]:
        """Deactivate active jobs their own board has stopped returning.

        The mass-removal guard withholds deletions when a board shrinks hard or
        comes back empty, which protects the corpus from a bad fetch but leaves
        the dropped jobs active. This closes that loop.

        Staleness is measured against the board's most recent *successful
        ingestion*, not against the newest surviving job. Those differ in the
        case that matters: when a board returns nothing at all, every job keeps
        the same last_seen_at, so no job is older than its neighbours and an
        age-relative-to-siblings rule can never fire. MeanPug sat in exactly
        that state. It also rules out a board nobody has fetched lately losing
        its jobs, because absence of a fetch is not evidence of absence.

        ingestion_runs is the source rather than ats_boards.updated_at, which a
        registry import also touches and would turn into a mass expiry.
        """
        with self.connection() as conn, conn.transaction():
            rows = conn.execute(
                """
                with last_success as (
                  select board_id, max(finished_at) as fetched_at
                  from public.ingestion_runs
                  where status = 'succeeded' and finished_at is not null
                  group by board_id
                )
                update public.jobs j
                set active = false,
                    removed_at = now(),
                    updated_at = now()
                from last_success s, public.ats_boards b
                where s.board_id = j.ats_board_id
                  and b.id = j.ats_board_id
                  and j.active
                  and j.last_seen_at < s.fetched_at - make_interval(days => %s)
                returning j.id, j.title, j.company_name, b.provider::text as provider,
                          b.board_key, j.last_seen_at
                """,
                (stale_after_days,),
            ).fetchall()
        return [dict(row) for row in rows]

    def enabled_boards(self) -> list[BoardRef]:
        """Load the private scan registry from Postgres without exposing it to clients."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select
                  c.slug as company_slug,
                  c.name as company_name,
                  b.provider,
                  b.board_key,
                  b.source_url,
                  b.region
                from public.ats_boards b
                join public.companies c on c.id = b.company_id
                where c.enabled and b.enabled
                order by c.priority desc, lower(c.name), b.provider, b.board_key
                """
            ).fetchall()
        return [
            BoardRef(
                provider=ATSProvider(row["provider"]),
                company_slug=row["company_slug"],
                company_name=row["company_name"],
                board_key=row["board_key"],
                source_url=row["source_url"],
                region=row["region"],
            )
            for row in rows
        ]

    def active_jobs(self) -> list[tuple[str, str, NormalizedJob]]:
        """Return job and revision identities with their normalized payload."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select j.id as job_id, r.id as revision_id, r.normalized_payload,
                       r.description_text
                from public.jobs j
                join public.job_revisions r on r.id = j.current_revision_id
                where j.active
                order by j.first_seen_at desc
                """
            ).fetchall()
        jobs = []
        for row in rows:
            payload = dict(row["normalized_payload"])
            payload["description_text"] = row["description_text"]
            payload["description_html"] = None
            jobs.append(
                (
                    str(row["job_id"]),
                    str(row["revision_id"]),
                    NormalizedJob.model_validate(payload),
                )
            )
        return jobs

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
                with effective_profile as (
                  select p.id, (
                    select max(pm.profile_version)
                    from public.job_matches pm
                    where pm.profile_id = p.id
                  ) as match_version
                  from public.profiles p
                  where p.id = %s
                ),
                effective_matches as (
                  select distinct on (m.job_id) m.*
                  from public.job_matches m
                  join effective_profile p on p.id = m.profile_id
                    and p.match_version = m.profile_version
                  order by m.job_id, m.updated_at desc
                ),
                deduplicated_matches as (
                  select m.*, row_number() over (
                    partition by public.normalize_job_part(j.company_name),
                                 public.normalize_job_part(j.title)
                    order by m.score desc,
                             (j.workplace_type = 'remote') desc,
                             (j.salary_min is not null) desc,
                             j.published_at desc nulls last,
                             j.id
                  ) as duplicate_rank
                  from effective_matches m
                  join public.jobs j on j.id = m.job_id
                  where m.eligible and j.active
                )
                select j.title, j.company_name, j.job_url, j.apply_url,
                       j.first_seen_at, m.score, m.matched_evidence, m.concerns
                from effective_profile p
                join deduplicated_matches m on m.profile_id = p.id
                join public.jobs j on j.id = m.job_id
                where m.duplicate_rank = 1
                  and m.score >= %s
                  and not exists (
                    select 1 from public.job_history h
                    where h.profile_id = m.profile_id
                      and (h.permanent or h.suppress_until > now())
                      and (
                        h.source_job_key = j.source_key
                        or h.fingerprint = public.normalize_job_part(j.company_name)
                          || '::' || public.normalize_job_part(j.title)
                      )
                  )
                order by m.score desc, j.first_seen_at desc
                limit %s
                """,
                (profile_id, minimum_score, limit),
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
                with effective_profile as (
                  select p.*
                  from public.profiles p
                  where p.slug = %s
                ),
                -- Discover is sticky: once a job qualifies it stays visible
                -- until the user actually deals with it. Scoping to the newest
                -- profile_version rebuilt the list on every rescore, so an
                -- untouched job silently vanished because a later pass ranked
                -- it lower. Aggregate across versions instead.
                job_level as (
                  select m.job_id,
                         bool_or(m.eligible) as ever_eligible,
                         max(m.score) as best_score
                  from public.job_matches m
                  join effective_profile p on p.id = m.profile_id
                  group by m.job_id
                ),
                latest_match as (
                  select distinct on (m.job_id) m.*
                  from public.job_matches m
                  join effective_profile p on p.id = m.profile_id
                  order by m.job_id, m.profile_version desc, m.updated_at desc
                ),
                effective_matches as (
                  select l.*, jl.best_score, jl.ever_eligible
                  from latest_match l
                  join job_level jl on jl.job_id = l.job_id
                  where jl.ever_eligible
                    and jl.best_score >= %s
                ),
                deduplicated_matches as (
                  select m.*, row_number() over (
                    partition by public.normalize_job_part(j.company_name),
                                 public.normalize_job_part(j.title)
                    order by m.best_score desc,
                             (j.workplace_type = 'remote') desc,
                             (j.salary_min is not null) desc,
                             j.published_at desc nulls last,
                             j.id
                  ) as duplicate_rank
                  from effective_matches m
                  join public.jobs j on j.id = m.job_id
                  where j.active
                )
                select j.id, j.title, j.company_name, c.slug as company_slug,
                       j.department, j.workplace_type, j.salary_min, j.salary_max,
                       j.salary_currency, j.salary_interval, j.job_url, j.apply_url,
                       j.published_at, j.source_updated_at, j.first_seen_at,
                       j.last_seen_at, b.provider, m.best_score as score, m.component_scores,
                       m.matched_evidence, m.concerns, m.explanation,
                       feedback.verdict as feedback_verdict,
                       feedback.wrong_reason_code as feedback_reason_code,
                       feedback.reason as feedback_reason,
                       r.description_text as compensation_text,
                       coalesce(l.label, 'Location unspecified') as location,
                       locations.records as locations,
                       prior.history_candidates,
                       revision_history.revision_count,
                       revision_history.latest_revision_at
                from effective_profile p
                join deduplicated_matches m on m.profile_id = p.id
                  and m.duplicate_rank = 1
                join public.jobs j on j.id = m.job_id
                join public.job_revisions r on r.id = j.current_revision_id
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
                left join lateral (
                  select jsonb_agg(jsonb_build_object(
                    'label', jl.label,
                    'city', jl.city,
                    'region', jl.region,
                    'country', jl.country,
                    'country_code', jl.country_code,
                    'is_primary', jl.is_primary,
                    'is_remote', jl.is_remote
                  ) order by jl.is_primary desc, jl.is_remote desc, jl.label) as records
                  from public.job_locations jl
                  where jl.job_id = j.id
                ) locations on true
                left join lateral (
                  select f.verdict, f.wrong_reason_code, f.reason
                  from public.match_feedback f
                  join public.jobs feedback_job on feedback_job.id = f.job_id
                  where f.profile_id = p.id
                    and (
                      f.job_id = j.id
                      or (
                        public.normalize_job_part(feedback_job.company_name)
                          = public.normalize_job_part(j.company_name)
                        and public.normalize_job_part(feedback_job.title)
                          = public.normalize_job_part(j.title)
                      )
                    )
                  order by (f.job_id = j.id) desc, f.updated_at desc
                  limit 1
                ) feedback on true
                left join lateral (
                  select jsonb_agg(jsonb_build_object(
                    'title', h.title,
                    'category', h.category,
                    'status', h.status,
                    'applied_at', h.applied_at,
                    'first_recorded_at', h.first_recorded_at
                  ) order by h.applied_at desc nulls last, h.first_recorded_at desc)
                    as history_candidates
                  from public.job_history h
                  where h.profile_id = p.id
                    and h.normalized_company = public.normalize_job_part(j.company_name)
                    and (h.permanent or h.suppress_until > now())
                ) prior on true
                left join lateral (
                  select count(*) as revision_count,
                         max(observed_at) as latest_revision_at
                  from public.job_revisions history
                  where history.job_id = j.id
                ) revision_history on true
                where m.ever_eligible and m.best_score >= %s
                  and (%s or not exists (
                    select 1 from public.job_history h
                    where h.profile_id = p.id
                      and (h.permanent or h.suppress_until > now())
                      and (
                        h.source_job_key = j.source_key
                        or h.fingerprint = public.normalize_job_part(j.company_name)
                          || '::' || public.normalize_job_part(j.title)
                      )
                  ))
                order by m.best_score desc, j.first_seen_at desc
                limit %s
                """,
                (profile_slug, STICKY_SCORE_FLOOR, minimum_score, include_suppressed, limit),
            ).fetchall()
        now = datetime.now(UTC)
        result = []
        for row in rows:
            item = dict(row)
            prior_application = None
            for candidate in item.pop("history_candidates", None) or []:
                comparison = compare_prior_job_titles(item["title"], candidate["title"])
                if comparison.likely_same_role and comparison.confidence < 1:
                    prior_application = {
                        **candidate,
                        "confidence": comparison.confidence,
                        "reason": comparison.reason,
                        "is_applied": (
                            candidate["category"].casefold() == "applied"
                            or "applied" in candidate["status"].casefold()
                        ),
                    }
                    break
            published = item["published_at"] or item["first_seen_at"]
            age_hours = max(0, int((now - published).total_seconds() / 3600))
            salary = None
            compensation_source = None
            salary_min = item["salary_min"]
            salary_max = item["salary_max"]
            salary_currency = item["salary_currency"]
            salary_interval = item["salary_interval"]
            if salary_min is not None:
                upper = salary_max or salary_min
                symbol = (
                    "$"
                    if salary_currency in {None, "USD"}
                    else {"GBP": "£", "EUR": "€"}.get(salary_currency, salary_currency)
                )
                if salary_interval == "hour":
                    lower_label = f"{symbol}{float(salary_min):,.0f}"
                    upper_label = f"{symbol}{float(upper):,.0f}"
                    salary = f"{lower_label}–{upper_label}/hour"
                else:
                    lower_label = f"{symbol}{float(salary_min) / 1000:,.0f}K"
                    upper_label = f"{symbol}{float(upper) / 1000:,.0f}K"
                    salary = f"{lower_label}–{upper_label}"
                compensation_source = compensation_source or "ATS"
            result.append(
                {
                    **item,
                    "id": str(item["id"]),
                    "company": item["company_name"],
                    "company_initial": item["company_name"][0],
                    "workplace": item["workplace_type"],
                    "compensation": salary,
                    "compensation_source": compensation_source,
                    "compensation_minimum": (
                        float(salary_min) if salary_min is not None else None
                    ),
                    "compensation_maximum": (
                        float(salary_max or salary_min)
                        if salary_min is not None
                        else None
                    ),
                    "compensation_currency": salary_currency,
                    "compensation_interval": salary_interval,
                    "score": float(item["score"]),
                    "desirability_score": round(
                        float(item["score"])
                        + float((item.get("component_scores") or {}).get("desirability_prior", 0)),
                        2,
                    ),
                    "evidence": item["matched_evidence"],
                    "freshness": (
                        f"{age_hours}h ago"
                        if age_hours < 48
                        else f"{age_hours // 24}d ago"
                    ),
                    "apply_url": item["apply_url"] or item["job_url"],
                    "prior_application": prior_application,
                }
            )
        return result

    def job_description(self, profile_slug: str, job_id: str) -> str | None:
        """Return one current full description after verifying profile visibility."""
        with self.connection() as conn:
            row = conn.execute(
                """
                with effective_profile as (
                  select p.id, (
                    select max(pm.profile_version)
                    from public.job_matches pm
                    where pm.profile_id = p.id
                  ) as match_version
                  from public.profiles p
                  where p.slug = %s
                ),
                effective_matches as (
                  select distinct on (m.job_id) m.*
                  from public.job_matches m
                  join effective_profile p on p.id = m.profile_id
                    and p.match_version = m.profile_version
                  order by m.job_id, m.updated_at desc
                )
                select r.description_text
                from effective_profile p
                join effective_matches m on m.profile_id = p.id
                join public.jobs j on j.id = m.job_id and j.active
                join public.job_revisions r on r.id = j.current_revision_id
                where j.id = %s
                  and m.eligible
                limit 1
                """,
                (profile_slug, job_id),
            ).fetchone()
        return row["description_text"] if row else None

    def role_thresholds(self, profile_slug: str) -> dict[str, int]:
        """Return saved role-family threshold overrides for a named profile."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select t.family_id, t.threshold
                from public.profile_role_thresholds t
                join public.profiles p on p.id = t.profile_id
                where p.slug = %s
                """,
                (profile_slug,),
            ).fetchall()
        return {row["family_id"]: int(row["threshold"]) for row in rows}

    def set_role_threshold(
        self,
        profile_slug: str,
        family_id: str,
        threshold: int,
    ) -> None:
        if not 0 <= threshold <= 100:
            raise ValueError("Threshold must be between 0 and 100")
        with self.connection() as conn:
            row = conn.execute(
                """
                insert into public.profile_role_thresholds (
                  profile_id, family_id, threshold
                )
                select id, %s, %s from public.profiles where slug = %s
                on conflict (profile_id, family_id) do update set
                  threshold = excluded.threshold,
                  updated_at = now()
                returning profile_id
                """,
                (family_id, threshold, profile_slug),
            ).fetchone()
            if row is None:
                raise LookupError("Profile not found")

    def reset_role_threshold(self, profile_slug: str, family_id: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                delete from public.profile_role_thresholds t
                using public.profiles p
                where t.profile_id = p.id
                  and p.slug = %s and t.family_id = %s
                """,
                (profile_slug, family_id),
            )

    def pipeline(self, profile_slug: str) -> dict:
        """Return durable campaign cards even when listings close or scores change."""
        stage_names = ("Considering", "Preparing", "Applied", "Interviewing", "Offer")
        stages = {name: [] for name in stage_names}
        with self.connection() as conn:
            rows = conn.execute(
                """
                select a.id as action_id, a.job_id, a.state, a.priority, a.notes,
                       a.follow_up_at, a.applied_at, a.closed_reason,
                       a.created_at as saved_at, a.updated_at as action_updated_at,
                       coalesce(se.created_at, a.created_at) as stage_changed_at,
                       j.title, j.company_name, j.department, j.workplace_type,
                       j.salary_min, j.salary_max, j.salary_currency,
                       j.salary_interval, j.job_url, j.apply_url, j.active,
                       j.published_at, j.first_seen_at, b.provider,
                       coalesce(l.label, 'Location unspecified') as location,
                       coalesce(m.score, 0) as score,
                       coalesce(m.component_scores, '{}'::jsonb) as component_scores,
                       coalesce(m.matched_evidence, '[]'::jsonb) as matched_evidence,
                       coalesce(m.concerns, '[]'::jsonb) as concerns,
                       coalesce(m.explanation, '') as explanation,
                       r.description_text
                from public.job_actions a
                join public.profiles p on p.id = a.profile_id
                join public.jobs j on j.id = a.job_id
                join public.ats_boards b on b.id = j.ats_board_id
                left join public.job_revisions r on r.id = j.current_revision_id
                left join lateral (
                  select pm.score, pm.component_scores, pm.matched_evidence,
                         pm.concerns, pm.explanation
                  from public.job_matches pm
                  where pm.profile_id = p.id
                    and pm.job_id = j.id
                    and pm.profile_version = (
                      select max(vm.profile_version)
                      from public.job_matches vm
                      where vm.profile_id = p.id
                    )
                  order by pm.updated_at desc
                  limit 1
                ) m on true
                left join lateral (
                  select created_at
                  from public.action_events
                  where profile_id = a.profile_id
                    and job_id = a.job_id
                    and event_type = 'state_changed'
                    and to_state = a.state
                  order by created_at desc
                  limit 1
                ) se on true
                left join lateral (
                  select label from public.job_locations
                  where job_id = j.id
                  order by is_primary desc, is_remote desc, label
                  limit 1
                ) l on true
                where p.slug = %s
                order by a.priority desc, a.follow_up_at nulls last, a.updated_at desc
                """,
                (profile_slug,),
            ).fetchall()
            events = conn.execute(
                """
                select e.job_id, e.event_type, e.from_state, e.to_state, e.note,
                       e.created_at
                from public.action_events e
                join public.profiles p on p.id = e.profile_id
                where p.slug = %s
                order by e.created_at desc
                limit 100
                """,
                (profile_slug,),
            ).fetchall()
        terminal = []
        now = datetime.now(UTC)
        for row in rows:
            item = dict(row)
            salary = None
            if item["salary_min"] is not None:
                upper = item["salary_max"] or item["salary_min"]
                symbol = (
                    "$"
                    if item["salary_currency"] in {None, "USD"}
                    else item["salary_currency"]
                )
                salary = (
                    f"{symbol}{float(item['salary_min']) / 1000:,.0f}K–"
                    f"{symbol}{float(upper) / 1000:,.0f}K"
                )
            age = max(0, (now - item["stage_changed_at"]).days)
            job = {
                **item,
                "id": str(item["job_id"]),
                "company": item["company_name"],
                "company_initial": item["company_name"][0],
                "compensation": salary,
                "score": float(item["score"]),
                "evidence": item["matched_evidence"],
                "component_scores": item["component_scores"],
                "concerns": item["concerns"],
                "explanation": item["explanation"],
                "provider": item["provider"],
                "freshness": "Listing closed" if not item["active"] else (
                    f"{max(0, (now - (item['published_at'] or item['first_seen_at'])).days)}d ago"
                ),
                "apply_url": item["apply_url"] or item["job_url"],
                "days_in_stage": age,
                "overdue": bool(item["follow_up_at"] and item["follow_up_at"] < now),
                "description_text": item["description_text"] or "",
            }
            if item["state"] in {"closed", "dismissed", "archived"}:
                terminal.append(job)
            else:
                stages[item["state"].title()].append(job)
        return {
            "stages": stages,
            "terminal": terminal,
            "events": [dict(event) for event in events],
        }

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

    def set_action(self, profile_slug: str, job_id: str, state: str) -> dict:
        allowed = {
            "considering", "preparing", "applied", "interviewing", "offer",
            "closed", "dismissed", "archived",
        }
        if state not in allowed:
            raise ValueError("Unsupported pipeline state")
        with self.connection() as conn, conn.transaction():
            previous = conn.execute(
                """
                select a.id, a.state
                from public.job_actions a
                join public.profiles p on p.id = a.profile_id
                where p.slug = %s and a.job_id = %s
                for update
                """,
                (profile_slug, job_id),
            ).fetchone()
            row = conn.execute(
                """
                insert into public.job_actions (profile_id, job_id, state)
                select p.id, j.id, %s::public.pipeline_state
                from public.profiles p, public.jobs j
                where p.slug = %s and j.id = %s
                  and (
                    j.active
                    or exists (
                      select 1 from public.job_actions existing
                      where existing.profile_id = p.id and existing.job_id = j.id
                    )
                  )
                on conflict (profile_id, job_id) do update
                  set state = excluded.state,
                      closed_reason = case
                        when excluded.state in (
                          'considering', 'preparing', 'applied',
                          'interviewing', 'offer'
                        ) then null
                        else job_actions.closed_reason
                      end,
                      updated_at = now()
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
                  profile_id, job_id, action_id, event_type, from_state, to_state
                ) values (
                  %s, %s, %s, 'state_changed',
                  %s::public.pipeline_state, %s::public.pipeline_state
                )
                """,
                (
                    row["profile_id"], row["job_id"], row["id"],
                    previous["state"] if previous else None, state,
                ),
            )
        return {"from_state": previous["state"] if previous else None, "to_state": state}

    def update_action_details(
        self,
        profile_slug: str,
        job_id: str,
        *,
        notes: str,
        priority: int,
        follow_up_at: datetime | None,
        closed_reason: str | None = None,
    ) -> None:
        if priority < -10 or priority > 10:
            raise ValueError("Priority must be between -10 and 10")
        clean_notes = notes.strip()[:4000]
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                update public.job_actions a
                set notes = %s, priority = %s, follow_up_at = %s,
                    closed_reason = %s, updated_at = now()
                from public.profiles p
                where p.id = a.profile_id and p.slug = %s and a.job_id = %s
                returning a.id, a.profile_id, a.job_id, a.state
                """,
                (
                    clean_notes, priority, follow_up_at,
                    closed_reason.strip()[:200] if closed_reason else None,
                    profile_slug, job_id,
                ),
            ).fetchone()
            if row is None:
                raise LookupError("Pipeline job not found")
            conn.execute(
                """
                insert into public.action_events (
                  profile_id, job_id, action_id, event_type, from_state, to_state,
                  note, metadata
                ) values (%s, %s, %s, 'details_updated', %s, %s, %s, %s)
                """,
                (
                    row["profile_id"], row["job_id"], row["id"], row["state"],
                    row["state"], clean_notes[:500],
                    json.dumps({"priority": priority, "follow_up_at": (
                        follow_up_at.isoformat() if follow_up_at else None
                    ), "closed_reason": closed_reason}),
                ),
            )

    def unsave_action(self, profile_slug: str, job_id: str) -> str:
        """Remove a bookmark without dismissing or suppressing the opportunity."""
        with self.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                select a.id, a.profile_id, a.job_id, a.state
                from public.job_actions a
                join public.profiles p on p.id = a.profile_id
                where p.slug = %s and a.job_id = %s
                for update
                """,
                (profile_slug, job_id),
            ).fetchone()
            if row is None:
                raise LookupError("Pipeline job not found")
            if row["state"] not in {"considering", "preparing"}:
                raise ValueError("Only saved or preparing jobs can be unsaved")
            conn.execute(
                """
                insert into public.action_events (
                  profile_id, job_id, action_id, event_type, from_state
                ) values (%s, %s, %s, 'unsaved', %s)
                """,
                (row["profile_id"], row["job_id"], row["id"], row["state"]),
            )
            conn.execute("delete from public.job_actions where id = %s", (row["id"],))
        return str(row["state"])

    def undo_action(self, profile_slug: str, job_id: str) -> str | None:
        """Reverse the most recent reversible state change for one job."""
        with self.connection() as conn, conn.transaction():
            event = conn.execute(
                """
                select e.id, e.event_type, e.from_state, e.to_state, e.profile_id
                from public.action_events e
                join public.profiles p on p.id = e.profile_id
                where p.slug = %s and e.job_id = %s
                  and e.event_type in ('state_changed', 'unsaved')
                order by e.created_at desc
                limit 1
                for update
                """,
                (profile_slug, job_id),
            ).fetchone()
            if event is None:
                raise LookupError("No action to undo")
            if event["event_type"] == "unsaved":
                target = event["from_state"]
                row = conn.execute(
                    """
                    insert into public.job_actions (profile_id, job_id, state)
                    values (%s, %s, %s)
                    on conflict (profile_id, job_id) do update
                      set state = excluded.state, updated_at = now()
                    returning id
                    """,
                    (event["profile_id"], job_id, target),
                ).fetchone()
            elif event["from_state"] is None:
                conn.execute(
                    "delete from public.job_actions where profile_id = %s and job_id = %s",
                    (event["profile_id"], job_id),
                )
                row = {"id": None}
                target = None
            else:
                target = event["from_state"]
                row = conn.execute(
                    """
                    update public.job_actions
                    set state = %s, updated_at = now()
                    where profile_id = %s and job_id = %s
                    returning id
                    """,
                    (target, event["profile_id"], job_id),
                ).fetchone()
            conn.execute(
                """
                insert into public.action_events (
                  profile_id, job_id, action_id, event_type, from_state, to_state,
                  metadata
                ) values (%s, %s, %s, 'undo', %s, %s, %s)
                """,
                (
                    event["profile_id"], job_id, row["id"],
                    event["to_state"], target,
                    json.dumps({"reversed_event_id": str(event["id"])}),
                ),
            )
            conn.execute(
                "update public.action_events set event_type = 'state_change_undone' where id = %s",
                (event["id"],),
            )
        return str(target) if target else None

    def set_match_feedback(
        self,
        profile_slug: str,
        job_id: str,
        verdict: str,
        *,
        wrong_reason_code: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Capture a durable quality verdict against the exact scored revision."""
        if verdict not in {"great", "maybe", "wrong", "duplicate"}:
            raise ValueError("Unsupported match verdict")
        clean_code = wrong_reason_code.strip() if wrong_reason_code else None
        if verdict == "wrong" and clean_code not in WRONG_REASON_CODES:
            raise ValueError("Choose why this match is wrong")
        if verdict != "wrong" and clean_code is not None:
            raise ValueError("Wrong-match reasons apply only to Wrong feedback")
        clean_reason = reason.strip()[:500] if reason and reason.strip() else None
        with self.connection() as conn, conn.transaction():
            target = conn.execute(
                """
                select p.id as profile_id, j.id as job_id, m.job_revision_id,
                       m.profile_version, m.score, m.component_scores
                from public.profiles p
                join public.jobs j on j.id = %s
                join lateral (
                  select fm.job_revision_id, fm.profile_version, fm.score,
                         fm.component_scores
                  from public.job_matches fm
                  where fm.profile_id = p.id and fm.job_id = j.id
                  order by fm.profile_version desc, fm.updated_at desc
                  limit 1
                ) m on true
                where p.slug = %s
                """,
                (job_id, profile_slug),
            ).fetchone()
            if target is None:
                raise LookupError("Current profile match not found")
            previous = conn.execute(
                """
                select verdict, wrong_reason_code, reason
                from public.match_feedback
                where profile_id = %s and job_id = %s
                """,
                (target["profile_id"], target["job_id"]),
            ).fetchone()
            conn.execute(
                """
                insert into public.match_feedback (
                  profile_id, job_id, job_revision_id, profile_version, verdict,
                  wrong_reason_code, reason, score_at_feedback, component_scores
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (profile_id, job_id)
                do update set job_revision_id = excluded.job_revision_id,
                              profile_version = excluded.profile_version,
                              verdict = excluded.verdict,
                              wrong_reason_code = excluded.wrong_reason_code,
                              reason = excluded.reason,
                              score_at_feedback = excluded.score_at_feedback,
                              component_scores = excluded.component_scores,
                              updated_at = now()
                """,
                (
                    target["profile_id"],
                    target["job_id"],
                    target["job_revision_id"],
                    target["profile_version"],
                    verdict,
                    clean_code,
                    clean_reason,
                    target["score"],
                    # dict_row returns jsonb as a plain dict, which psycopg
                    # cannot adapt back to a jsonb parameter on its own.
                    Jsonb(target["component_scores"]),
                ),
            )
            conn.execute(
                """
                insert into public.match_feedback_events (
                  profile_id, job_id, action, prior_verdict, verdict,
                  wrong_reason_code, reason
                ) values (%s, %s, 'set', %s, %s, %s, %s)
                """,
                (
                    target["profile_id"],
                    target["job_id"],
                    previous["verdict"] if previous else None,
                    verdict,
                    clean_code,
                    clean_reason,
                ),
            )

    def clear_match_feedback(self, profile_slug: str, job_id: str) -> None:
        """Remove a job's active verdict while retaining an audit event."""
        with self.connection() as conn, conn.transaction():
            previous = conn.execute(
                """
                select f.profile_id, f.job_id, f.verdict,
                       f.wrong_reason_code, f.reason
                from public.match_feedback f
                join public.profiles p on p.id = f.profile_id
                where p.slug = %s and f.job_id = %s
                """,
                (profile_slug, job_id),
            ).fetchone()
            if previous is None:
                raise LookupError("No match feedback to undo")
            conn.execute(
                """
                delete from public.match_feedback
                where profile_id = %s and job_id = %s
                """,
                (previous["profile_id"], previous["job_id"]),
            )
            conn.execute(
                """
                insert into public.match_feedback_events (
                  profile_id, job_id, action, prior_verdict, verdict,
                  wrong_reason_code, reason
                ) values (%s, %s, 'cleared', %s, null, %s, %s)
                """,
                (
                    previous["profile_id"],
                    previous["job_id"],
                    previous["verdict"],
                    previous["wrong_reason_code"],
                    previous["reason"],
                ),
            )

    def match_quality(self, profile_slug: str) -> dict:
        """Return transparent quality metrics from explicit human verdicts."""
        with self.connection() as conn:
            summary = conn.execute(
                """
                select count(*) as reviewed,
                       count(*) filter (where f.verdict = 'great') as great,
                       count(*) filter (where f.verdict = 'maybe') as maybe,
                       count(*) filter (where f.verdict = 'wrong') as wrong,
                       count(*) filter (where f.verdict = 'duplicate') as duplicate,
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
                select wrong_reason_code, count(*) as count
                from public.match_feedback f
                join public.profiles p on p.id = f.profile_id
                where p.slug = %s and f.verdict = 'wrong'
                group by wrong_reason_code
                order by count(*) desc, wrong_reason_code
                limit 8
                """,
                (profile_slug,),
            ).fetchall()
        reviewed = int(summary["reviewed"])
        useful = int(summary["great"]) + int(summary["maybe"])
        rated = useful + int(summary["wrong"])
        return {
            **dict(summary),
            "reviewed": reviewed,
            "useful_rate": round(100 * useful / rated, 1) if rated else None,
            "wrong_reasons": [dict(row) for row in reasons],
        }

    def wrong_feedback_records(self, profile_slug: str) -> list[dict]:
        """Return active Wrong verdicts with the evidence needed for MD calibration."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                select
                  j.title,
                  j.company_name,
                  coalesce(j.apply_url, j.job_url) as job_url,
                  f.wrong_reason_code,
                  f.reason,
                  f.score_at_feedback,
                  f.component_scores,
                  m.matched_evidence,
                  m.concerns,
                  left(r.description_text, 3000) as description_excerpt,
                  f.updated_at
                from public.match_feedback f
                join public.profiles p on p.id = f.profile_id
                join public.jobs j on j.id = f.job_id
                join public.job_revisions r on r.id = f.job_revision_id
                left join public.job_matches m
                  on m.profile_id = f.profile_id
                  and m.job_id = f.job_id
                  and m.job_revision_id = f.job_revision_id
                  and m.profile_version = f.profile_version
                where p.slug = %s and f.verdict = 'wrong'
                order by f.updated_at desc, j.company_name, j.title
                """,
                (profile_slug,),
            ).fetchall()
        return [dict(row) for row in rows]

    def market_intelligence(self, profile_slug: str) -> dict:
        """Return factual market and search-funnel aggregates for one profile."""
        with self.connection() as conn:
            overview = conn.execute(
                """
                with profile as (
                  select id, profile_version
                  from public.profiles where slug = %s
                ),
                current_matches as (
                  select m.eligible, m.score, j.workplace_type, j.salary_min
                  from public.job_matches m
                  join profile p on p.id = m.profile_id
                    and p.profile_version = m.profile_version
                  join public.jobs j on j.id = m.job_id
                    and j.current_revision_id = m.job_revision_id
                    and j.active
                )
                select
                  (select min(first_seen_at) from public.jobs) as observed_since,
                  (select count(*) from public.jobs where active) as active_jobs,
                  count(*) as scored_jobs,
                  count(*) filter (where eligible) as eligible_jobs,
                  count(*) filter (where eligible and score >= 70) as score_70_plus,
                  count(*) filter (where eligible and score >= 80) as score_80_plus,
                  count(*) filter (where eligible and score >= 88) as score_88_plus,
                  max(score) filter (where eligible) as maximum_score,
                  count(*) filter (
                    where eligible and workplace_type = 'remote'
                  ) as remote_eligible,
                  count(*) filter (
                    where eligible and salary_min is not null
                  ) as structured_salary_eligible,
                  (select count(*) from public.job_actions a
                    join profile p on p.id = a.profile_id
                    where a.state in ('considering', 'preparing')) as saved_jobs,
                  (select count(*) from public.job_actions a
                    join profile p on p.id = a.profile_id
                    where a.applied_at is not null) as tracked_applications,
                  (select count(*) from public.job_actions a
                    join profile p on p.id = a.profile_id
                    where a.state in ('interviewing', 'offer')) as active_responses,
                  (select count(*) from public.job_history h
                    join profile p on p.id = h.profile_id
                    where h.category = 'Applied') as historical_applications,
                  (select count(*) from public.jobs
                    where active and first_seen_at >= now() - interval '24 hours')
                    as new_jobs_24h,
                  (select count(*) from public.jobs
                    where removed_at >= now() - interval '7 days') as removed_jobs_7d
                from current_matches
                """,
                (profile_slug,),
            ).fetchone()
            providers = conn.execute(
                """
                with profile as (
                  select id, profile_version
                  from public.profiles where slug = %s
                ),
                current_matches as (
                  select m.job_id, m.job_revision_id, m.eligible, m.score
                  from public.job_matches m
                  join profile p on p.id = m.profile_id
                    and p.profile_version = m.profile_version
                )
                select b.provider,
                       count(distinct b.id) as board_count,
                       count(distinct j.id) filter (where j.active) as active_jobs,
                       count(distinct j.id) filter (
                         where j.active and m.eligible
                           and m.job_revision_id = j.current_revision_id
                       ) as eligible_jobs,
                       count(distinct j.id) filter (
                         where j.active and m.eligible and m.score >= 70
                           and m.job_revision_id = j.current_revision_id
                       ) as strong_jobs
                from public.ats_boards b
                left join public.jobs j on j.ats_board_id = b.id
                left join current_matches m on m.job_id = j.id
                where b.enabled
                group by b.provider
                order by eligible_jobs desc, active_jobs desc
                """,
                (profile_slug,),
            ).fetchall()
            excluded = conn.execute(
                """
                with profile as (
                  select id, profile_version
                  from public.profiles where slug = %s
                )
                select concern, count(*) as count
                from public.job_matches m
                join profile p on p.id = m.profile_id
                  and p.profile_version = m.profile_version
                join public.jobs j on j.id = m.job_id
                  and j.current_revision_id = m.job_revision_id and j.active
                cross join lateral jsonb_array_elements_text(m.concerns) concern
                where not m.eligible
                group by concern
                order by count(*) desc, concern
                limit 8
                """,
                (profile_slug,),
            ).fetchall()
        return {
            "overview": dict(overview),
            "providers": [dict(row) for row in providers],
            "exclusions": [dict(row) for row in excluded],
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

    def fail_interrupted_scans(self, stale_after_hours: int = 3) -> int:
        """Close scan records orphaned by a killed worker.

        Staleness is decided by age, not by the scan lock. Provider shards run
        concurrently under separate locks, so holding one no longer proves that
        no other scan is active, and failing every ``running`` row would mark
        the other shards' live runs as failed the moment they started.

        The scheduled job times out at 60 minutes, so a run still ``running``
        well past that was abandoned by a killed worker and nothing will ever
        close it.
        """
        with self.connection() as conn, conn.transaction():
            result = conn.execute(
                """
                update public.scan_runs
                set status = 'failed'::public.run_status,
                    finished_at = now(),
                    failed_count = greatest(failed_count, board_count - succeeded_count),
                    error_codes = (
                      select jsonb_agg(distinct value order by value)
                      from jsonb_array_elements_text(
                        coalesce(error_codes, '[]'::jsonb) || '["interrupted"]'::jsonb
                      ) as errors(value)
                    )
                where status = 'running'
                  and started_at < now() - make_interval(hours => %s)
                """,
                (stale_after_hours,),
            )
        return result.rowcount

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
        """Import a private local registry into the live database."""
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
                            json.dumps({"managed_by": "private_database_registry"}),
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
                    removal_withheld=plan.removal_withheld,
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

            current_rows = conn.execute(
                """
                select j.source_key, r.content_hash
                from public.jobs j
                left join public.job_revisions r on r.id = j.current_revision_id
                where j.ats_board_id = %s
                """,
                (board_id,),
            ).fetchall()
            current_hashes = {
                row["source_key"]: row["content_hash"] for row in current_rows
            }
            changed_jobs, updated_count = jobs_requiring_upsert(jobs, current_hashes)

            if jobs:
                conn.execute(
                    """
                    update public.jobs
                    set last_seen_at = now(), active = true, removed_at = null
                    where ats_board_id = %s and source_job_id = any(%s)
                    """,
                    (board_id, [job.source_job_id for job in jobs]),
                )

            for job in changed_jobs:
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
                compact_payload = job.model_dump(
                    mode="json",
                    exclude={"description_text", "description_html"},
                )
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
                        None,
                        "",
                        json.dumps(compact_payload),
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
            removal_withheld=plan.removal_withheld,
        )
