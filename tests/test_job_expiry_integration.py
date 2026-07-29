"""Integration tests for expiring jobs a board has stopped returning.

These run against a real Postgres because the behaviour is a SQL update over
board-level aggregates, and a mock asserting on query text would not catch the
thing that actually went wrong.

Skipped automatically when no local database is reachable.
Start the stack with:  supabase start
"""

from __future__ import annotations

import os
import uuid

import pytest

from ferminator.repository import PostgresRepository

LOCAL_DB_URL = os.environ.get(
    "FERMINATOR_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)


def _database_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(LOCAL_DB_URL, connect_timeout=2):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(),
    reason="local Postgres not reachable; run `supabase start`",
)


@pytest.fixture
def repository():
    repo = PostgresRepository(LOCAL_DB_URL)
    yield repo
    repo.close()


@pytest.fixture
def board_with_a_dropped_job():
    """One board: a job seen just now, and one last seen well before that.

    This is the shape a withheld removal leaves behind. Yields
    ``(fresh_job_id, stale_job_id, board_id, company_id)``.
    """
    import psycopg

    suffix = uuid.uuid4().hex[:8]
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        company_id = conn.execute(
            "insert into public.companies (slug, name, enabled, priority) "
            "values (%s, %s, true, 50) returning id",
            (f"expiry-co-{suffix}", f"Expiry Co {suffix}"),
        ).fetchone()[0]
        board_id = conn.execute(
            "insert into public.ats_boards "
            "(company_id, provider, board_key, region, source_url, enabled) "
            "values (%s, 'greenhouse', %s, 'global', %s, true) returning id",
            (company_id, f"expiry-{suffix}", f"https://example.test/{suffix}"),
        ).fetchone()[0]
        ids = []
        for key, seen in (("fresh", "now()"), ("stale", "now() - interval '9 days'")):
            ids.append(
                conn.execute(
                    "insert into public.jobs (ats_board_id, source_job_id, source_key, "
                    " company_name, title, job_url, active, first_seen_at, last_seen_at) "
                    f"values (%s, %s, %s, %s, %s, %s, true, now() - interval '20 days', {seen}) "
                    "returning id",
                    (board_id, f"{key}-{suffix}", f"greenhouse:{key}-{suffix}",
                     "Expiry Co", f"{key.title()} Role", f"https://example.test/{key}"),
                ).fetchone()[0]
            )
    yield ids[0], ids[1], board_id, company_id
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute("delete from public.jobs where ats_board_id = %s", (board_id,))
        conn.execute("delete from public.ats_boards where id = %s", (board_id,))
        conn.execute("delete from public.companies where id = %s", (company_id,))


def _active(job_id) -> bool:
    import psycopg

    with psycopg.connect(LOCAL_DB_URL) as conn:
        return conn.execute("select active from public.jobs where id = %s", (job_id,)).fetchone()[0]


def test_a_job_its_board_stopped_returning_is_expired(repository, board_with_a_dropped_job):
    """Regression: Jerry.ai's pulled roles stayed active and were rated Great.

    The removal guard withheld the deletion, correctly, but nothing ever closed
    the loop afterwards, so the dead listings were served as live matches.
    """
    fresh_id, stale_id, _board, _co = board_with_a_dropped_job

    expired = repository.expire_unseen_jobs(stale_after_days=3)

    assert stale_id in {row["id"] for row in expired}
    assert not _active(stale_id), "a job the board no longer returns must be expired"
    assert _active(fresh_id), "a job the board still returns must survive"


def test_expiry_leaves_a_board_that_is_merely_stale_alone(repository, board_with_a_dropped_job):
    """A board nobody has fetched recently must not lose its jobs.

    Absence of a fetch is not evidence that the listings disappeared, so expiry
    keys on a job being older than its own board's most recent sighting.
    """
    import psycopg

    fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    # Push the whole board into the past: now nothing was seen more recently
    # than anything else, so there is no evidence any single job was dropped.
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "update public.jobs set last_seen_at = now() - interval '30 days' "
            "where ats_board_id = %s",
            (board_id,),
        )

    repository.expire_unseen_jobs(stale_after_days=3)

    assert _active(fresh_id)
    assert _active(stale_id), "a uniformly stale board must not be gutted"


def test_expiry_respects_the_grace_period(repository, board_with_a_dropped_job):
    """A job dropped only moments ago is not yet evidence of anything."""
    _fresh_id, stale_id, _board, _co = board_with_a_dropped_job

    repository.expire_unseen_jobs(stale_after_days=30)

    assert _active(stale_id), "9 days old must survive a 30 day grace period"
