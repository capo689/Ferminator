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


def _record_success(board_id, when: str, withheld: str | None = None) -> None:
    """Record a succeeded ingestion run, which is what expiry measures against.

    `withheld` marks the run as guarded by the mass-removal protection, which
    makes it a non-authoritative snapshot of the board.
    """
    import uuid as _uuid

    import psycopg

    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "insert into public.ingestion_runs "
            "(board_id, provider, idempotency_key, status, started_at, finished_at, "
            " removal_withheld) "
            f"values (%s, 'greenhouse', %s, 'succeeded', {when}, {when}, %s)",
            (board_id, f"test-{_uuid.uuid4().hex}", withheld),
        )


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
        conn.execute("delete from public.ingestion_runs where board_id = %s", (board_id,))
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
    fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    _record_success(board_id, "now()")

    expired = repository.expire_unseen_jobs(stale_after_days=3)

    assert stale_id in {row["id"] for row in expired}
    assert not _active(stale_id), "a job the board no longer returns must be expired"
    assert _active(fresh_id), "a job the board still returns must survive"


def test_a_board_nobody_has_fetched_keeps_its_jobs(repository, board_with_a_dropped_job):
    """Absence of a fetch is not evidence the listings disappeared.

    A board whose last success is itself old must lose nothing, or an outage on
    our side would quietly empty the corpus.
    """
    fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    _record_success(board_id, "now() - interval '30 days'")

    repository.expire_unseen_jobs(stale_after_days=3)

    assert _active(fresh_id)
    assert _active(stale_id), "a board we have not fetched must not be gutted"


def test_an_empty_board_still_expires_its_jobs(repository, board_with_a_dropped_job):
    """Regression: MeanPug. This is the case the first version could not reach.

    When a board returns nothing, every job keeps the same last_seen_at, so a
    rule comparing a job against its newest sibling never fires and the board
    holds dead listings forever. Measuring against the board's last successful
    fetch is what makes an empty board converge.
    """
    import psycopg

    fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    # Nothing came back, so no job was refreshed: they all share one timestamp.
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "update public.jobs set last_seen_at = now() - interval '9 days' "
            "where ats_board_id = %s",
            (board_id,),
        )
    _record_success(board_id, "now()")

    expired = repository.expire_unseen_jobs(stale_after_days=3)

    expired_ids = {row["id"] for row in expired}
    assert fresh_id in expired_ids and stale_id in expired_ids, (
        "an empty board that keeps fetching successfully must expire everything"
    )


def test_expiry_respects_the_grace_period(repository, board_with_a_dropped_job):
    """A job dropped only moments ago is not yet evidence of anything."""
    _fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    _record_success(board_id, "now()")

    repository.expire_unseen_jobs(stale_after_days=30)

    assert _active(stale_id), "9 days old must survive a 30 day grace period"


def test_a_guarded_run_does_not_expire_what_the_guard_protected(
    repository, board_with_a_dropped_job
):
    """Regression: the guard blocked the delete, expiry did it three days later.

    A run that tripped the mass-removal guard finishes successfully, so it used
    to advance the same clock expiry measures against. The jobs the bad
    response omitted never had last_seen_at refreshed, so expiry deactivated
    exactly the set the guard had just refused to remove.
    """
    fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    _record_success(board_id, "now()", withheld="Empty response would remove every active job")

    expired = repository.expire_unseen_jobs(stale_after_days=3, trust_withheld_after=3)

    assert expired == [], "a single guarded run must not expire anything"
    assert _active(stale_id)
    assert _active(fresh_id)


def test_a_persistently_guarded_board_is_eventually_believed(
    repository, board_with_a_dropped_job
):
    """A board that keeps reporting the same guarded result is telling the truth.

    Ignoring guarded runs forever would freeze a genuinely emptied board, which
    is the failure MeanPug sat in. After enough consecutive guarded runs the
    latest one becomes the reference and the board converges.
    """
    _fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    for _ in range(3):
        _record_success(board_id, "now()", withheld="Empty response would remove every active job")

    expired = repository.expire_unseen_jobs(stale_after_days=3, trust_withheld_after=3)

    assert stale_id in {row["id"] for row in expired}
    assert not _active(stale_id)


def test_one_clean_run_resets_the_guarded_streak(repository, board_with_a_dropped_job):
    """A clean run breaks the streak, so the reference stays the trusted run.

    The arithmetic here is deliberate. The job was last seen 4 days ago, the
    last clean run was 10 days ago, and a guarded run just finished. Measuring
    against the clean run leaves the job alone; measuring against the guarded
    run would expire it. Only the first is correct.
    """
    import psycopg

    _fresh_id, stale_id, board_id, _co = board_with_a_dropped_job
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "update public.jobs set last_seen_at = now() - interval '4 days' where id = %s",
            (stale_id,),
        )
    _record_success(board_id, "now() - interval '10 days'")
    _record_success(board_id, "now()", withheld="guarded")

    repository.expire_unseen_jobs(stale_after_days=3, trust_withheld_after=3)

    assert _active(stale_id), (
        "one guarded run does not meet the streak, so the 10-day-old clean run "
        "is the reference and a job seen 4 days ago is not yet stale against it"
    )
