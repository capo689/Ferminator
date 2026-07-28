"""Integration tests for concurrent provider shards.

The scheduled scan fans out into three shards that run at the same time. These
tests cover the two places that assumed only one scan process ever existed.

Skipped automatically when no local database is reachable.

Start the stack with:  supabase start
"""

from __future__ import annotations

import os
import uuid

import pytest

from ferminator.repository import ConcurrentScanError, PostgresRepository

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
def scan_rows():
    """Insert one just-started run and one long-abandoned run."""
    import psycopg

    suffix = uuid.uuid4().hex[:8]
    fresh_key, stale_key = f"fresh-{suffix}", f"stale-{suffix}"
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "insert into public.scan_runs (idempotency_key, status, board_count, started_at) "
            "values (%s, 'running', 10, now())",
            (fresh_key,),
        )
        conn.execute(
            "insert into public.scan_runs (idempotency_key, status, board_count, started_at) "
            "values (%s, 'running', 10, now() - interval '9 hours')",
            (stale_key,),
        )
    yield fresh_key, stale_key
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "delete from public.scan_runs where idempotency_key = any(%s)",
            ([fresh_key, stale_key],),
        )


def _status(key: str) -> str:
    import psycopg

    with psycopg.connect(LOCAL_DB_URL) as conn:
        return conn.execute(
            "select status::text from public.scan_runs where idempotency_key = %s", (key,)
        ).fetchone()[0]


def test_interrupted_sweep_spares_a_concurrently_running_shard(repository, scan_rows):
    """Regression: shard 2 starting must not fail shard 1's live run.

    fail_interrupted_scans() used to fail every row with status 'running',
    relying on a single global scan lock to prove nothing else was active. Once
    provider shards took separate locks and ran in parallel, each starting shard
    marked the already-running shards as failed.
    """
    fresh_key, stale_key = scan_rows

    repository.fail_interrupted_scans()

    assert _status(fresh_key) == "running", (
        "a shard that started moments ago is still alive and must not be failed"
    )
    assert _status(stale_key) == "failed", "a run abandoned hours ago must still be closed"


def test_provider_shards_hold_independent_locks(repository):
    """Two providers must be able to pull at the same time."""
    other = PostgresRepository(LOCAL_DB_URL)
    try:
        with repository.scan_lock("scan:greenhouse:1of3"):
            with other.scan_lock("scan:workday:2of3"):
                pass  # both held at once, which is the whole point
    finally:
        other.close()


def test_same_shard_still_refuses_to_double_run(repository):
    """Independent locks must not weaken the guard within one shard."""
    other = PostgresRepository(LOCAL_DB_URL)
    try:
        with repository.scan_lock("scan:greenhouse:1of3"):
            with pytest.raises(ConcurrentScanError):
                with other.scan_lock("scan:greenhouse:1of3"):
                    pass
    finally:
        other.close()
