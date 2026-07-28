"""Integration test for recording match feedback.

Runs against a real Postgres (the local Supabase stack) because the bug it
covers is a psycopg parameter-adaptation failure that only surfaces against a
live driver. A mock asserting on SQL text cannot catch it.

Skipped automatically when no local database is reachable.

Start the stack with:  supabase start
"""

from __future__ import annotations

import json
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
def seeded_match():
    """Insert a profile, job, revision and scored match; yield (slug, job_id)."""
    import psycopg

    suffix = uuid.uuid4().hex[:8]
    slug = f"fb-{suffix}"
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        profile_id = conn.execute(
            "insert into public.profiles (slug,display_name,source_path,source_hash,compiled_profile) "
            "values (%s,'Test',%s,'h','{}'::jsonb) returning id",
            (slug, f"db://{slug}"),
        ).fetchone()[0]
        company_id = conn.execute(
            "insert into public.companies (slug,name) values (%s,'Acme') returning id",
            (f"co-{suffix}",),
        ).fetchone()[0]
        board_id = conn.execute(
            "insert into public.ats_boards (company_id,provider,board_key,source_url) "
            "values (%s,'greenhouse',%s,'https://example.com') returning id",
            (company_id, f"bk-{suffix}"),
        ).fetchone()[0]
        job_id = conn.execute(
            "insert into public.jobs "
            "(ats_board_id,source_job_id,source_key,company_name,title,job_url,active) "
            "values (%s,'1',%s,'Acme','Editorial Lead','https://example.com/j',true) returning id",
            (board_id, f"sk-{suffix}"),
        ).fetchone()[0]
        revision_id = conn.execute(
            "insert into public.job_revisions (job_id,content_hash,normalized_payload) "
            "values (%s,'r1','{}'::jsonb) returning id",
            (job_id,),
        ).fetchone()[0]
        conn.execute(
            "update public.jobs set current_revision_id=%s where id=%s", (revision_id, job_id)
        )
        conn.execute(
            "insert into public.job_matches "
            "(profile_id,job_id,job_revision_id,profile_version,score,component_scores,eligible) "
            "values (%s,%s,%s,1,72.5,%s,true)",
            (profile_id, job_id, revision_id, json.dumps({"skills": 11.25, "geography": 10})),
        )

    yield slug, str(job_id)

    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute("delete from public.profiles where slug=%s", (slug,))
        conn.execute("delete from public.companies where slug=%s", (f"co-{suffix}",))


@pytest.fixture
def repository():
    repo = PostgresRepository(LOCAL_DB_URL)
    yield repo
    repo.close()


def test_recording_feedback_round_trips_component_scores(repository, seeded_match):
    """Regression: every Wrong/Great/Maybe click returned 500.

    component_scores is read back by dict_row as a plain Python dict and passed
    straight into the insert. psycopg cannot adapt a bare dict to jsonb:

        psycopg.ProgrammingError: cannot adapt type 'dict' using placeholder '%s'

    It needs an explicit Jsonb() wrapper.
    """
    import psycopg

    slug, job_id = seeded_match

    repository.set_match_feedback(
        slug, job_id, "wrong", wrong_reason_code="function_mismatch", reason="not my function"
    )
    with psycopg.connect(LOCAL_DB_URL) as conn:
        verdict, code, reason, scores = conn.execute(
            "select f.verdict, f.wrong_reason_code, f.reason, f.component_scores "
            "from public.match_feedback f join public.profiles p on p.id=f.profile_id "
            "where p.slug=%s",
            (slug,),
        ).fetchone()
    assert verdict == "wrong"
    assert code == "function_mismatch"
    assert reason == "not my function"
    assert scores == {"skills": 11.25, "geography": 10}, "jsonb must survive the round trip"


def test_re_rating_an_existing_verdict_succeeds(repository, seeded_match):
    """Re-rating takes the ON CONFLICT branch, which re-passes component_scores."""
    import psycopg

    slug, job_id = seeded_match
    repository.set_match_feedback(slug, job_id, "wrong", wrong_reason_code="too_technical")
    repository.set_match_feedback(slug, job_id, "maybe")

    with psycopg.connect(LOCAL_DB_URL) as conn:
        verdict, code = conn.execute(
            "select f.verdict, f.wrong_reason_code from public.match_feedback f "
            "join public.profiles p on p.id=f.profile_id where p.slug=%s",
            (slug,),
        ).fetchone()
        events = conn.execute(
            "select count(*) from public.match_feedback_events e "
            "join public.profiles p on p.id=e.profile_id where p.slug=%s",
            (slug,),
        ).fetchone()[0]

    assert verdict == "maybe"
    assert code is None, "clearing Wrong must clear its reason code"
    assert events == 2, "each change writes an audit event"
