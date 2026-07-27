"""Integration tests for scanner profile enumeration.

These run against a real Postgres (the local Supabase stack) rather than a
mock, because the bug they cover is precisely that the scanner never consulted
the database. A mock asserting on SQL substrings cannot catch that.

Note the identity of a returned entry is its profile_id, not the parsed slug:
the slug comes from the Markdown front matter, so two rows sharing a body
legitimately parse to the same slug.

Skipped automatically when no local database is reachable, so CI and laptops
without Docker stay green.

Start the stack with:  supabase start
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from ferminator.profiles import load_profile
from ferminator.repository import PostgresRepository

LOCAL_DB_URL = os.environ.get(
    "FERMINATOR_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)
PROFILE_FIXTURE = "profiles/adam-cagle.md"


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
def two_profiles():
    """Create one file-backed and one database-backed profile.

    This mirrors production exactly. `adam-cagle` predates database-hosted
    onboarding Markdown and still points at a file on disk, while anything
    provisioned through /admin exists only as a row under a db:// source path.
    Yields ``(file_backed_id, db_backed_id)``.
    """
    import psycopg

    compiled = load_profile(PROFILE_FIXTURE).model_dump(
        mode="json", exclude={"markdown_body", "source_path", "source_hash"}
    )
    raw_markdown = open(PROFILE_FIXTURE, encoding="utf-8").read()

    suffix = uuid.uuid4().hex[:8]
    rows = (
        (f"file-backed-{suffix}", PROFILE_FIXTURE, None),
        (f"db-backed-{suffix}", f"db://profiles/db-backed-{suffix}/v1.md", raw_markdown),
    )
    ids: list[str] = []
    auth_ids: list[str] = []

    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        for slug, source_path, markdown in rows:
            auth_id = str(uuid.uuid4())
            conn.execute(
                "insert into auth.users (id, instance_id, aud, role, email) "
                "values (%s, '00000000-0000-0000-0000-000000000000', "
                "'authenticated', 'authenticated', %s)",
                (auth_id, f"{slug}@example.test"),
            )
            profile_id = conn.execute(
                "insert into public.profiles "
                "(slug, display_name, source_path, source_hash, compiled_profile, "
                " onboarding_markdown, scan_enabled) "
                "values (%s, %s, %s, %s, %s, %s, true) returning id",
                (slug, slug, source_path, f"hash-{suffix}", json.dumps(compiled), markdown),
            ).fetchone()[0]
            conn.execute(
                "insert into public.accounts "
                "(auth_user_id, profile_id, username, email, role, status) "
                "values (%s, %s, %s, %s, 'user', 'active')",
                (auth_id, profile_id, slug.replace("-", "")[:32], f"{slug}@example.test"),
            )
            ids.append(str(profile_id))
            auth_ids.append(auth_id)

    yield ids[0], ids[1]

    # Order matters: accounts references auth.users and profiles with
    # ON DELETE RESTRICT, so the account rows have to go first.
    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute("delete from public.accounts where profile_id = any(%s::uuid[])", (ids,))
        conn.execute("delete from public.profiles where id = any(%s::uuid[])", (ids,))
        conn.execute("delete from auth.users where id = any(%s::uuid[])", (auth_ids,))


def test_scanner_sees_database_backed_profiles(repository, two_profiles):
    """Regression: an /admin-provisioned account was never scored.

    The scanner enumerated profiles with Path("profiles").glob("*.md"), so a
    profile whose Markdown lives in its row -- every account created through
    the admin control plane -- was invisible. Those users could sign in and
    would see an empty dashboard forever, with no error raised anywhere.
    """
    file_backed_id, db_backed_id = two_profiles
    returned = {profile_id for profile_id, _ in repository.scannable_profiles()}

    assert db_backed_id in returned, (
        "database-backed profile must be scannable; this is the ghost-account bug"
    )
    assert file_backed_id in returned, "file-backed profiles must keep working"


def test_scannable_profiles_hydrate_into_usable_profiles(repository, two_profiles):
    """Each entry must carry a real id and a parsed profile the matcher can score."""
    entries = repository.scannable_profiles()
    assert entries, "expected at least the two fixture profiles"
    for profile_id, profile in entries:
        uuid.UUID(profile_id)  # raises if it is not a real id
        assert profile.profile.slug
        assert profile.search is not None


def test_suspended_accounts_are_not_scanned(repository, two_profiles):
    """A paused or suspended account must drop out of the scan set."""
    import psycopg

    _, db_backed_id = two_profiles
    assert db_backed_id in {pid for pid, _ in repository.scannable_profiles()}

    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "update public.accounts set status = 'suspended' where profile_id = %s",
            (db_backed_id,),
        )

    assert db_backed_id not in {pid for pid, _ in repository.scannable_profiles()}, (
        "suspending an account must remove it from the scan set"
    )


def test_scan_disabled_profiles_are_not_scanned(repository, two_profiles):
    """profiles.scan_enabled = false must also drop the profile."""
    import psycopg

    _, db_backed_id = two_profiles

    with psycopg.connect(LOCAL_DB_URL, autocommit=True) as conn:
        conn.execute(
            "update public.profiles set scan_enabled = false where id = %s",
            (db_backed_id,),
        )

    assert db_backed_id not in {pid for pid, _ in repository.scannable_profiles()}
