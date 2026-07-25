"""Tests for scripts/backfill_salaries.py's DB path resolution."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from anthropic_tracker.db import get_connection, init_db

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "backfill_salaries.py"


def _load_backfill_module():
    """Import scripts/backfill_salaries.py directly since scripts/ isn't a package."""
    spec = importlib.util.spec_from_file_location("backfill_salaries", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_job(db_path, job_id=1):
    conn = get_connection(str(db_path))
    init_db(conn)
    conn.execute(
        """INSERT INTO jobs (id, title, first_seen, last_seen, removed_date)
           VALUES (?, 'Test Job', '2026-07-22', '2026-07-22', NULL)""",
        (job_id,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def two_company_env(tmp_path, monkeypatch):
    """Seed separate DBs for two companies and point config at them."""
    monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
    monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
    _seed_job(tmp_path / "tracker-anthropic.db", job_id=1)
    _seed_job(tmp_path / "tracker-openai.db", job_id=2)
    return tmp_path


class TestBackfillDbPathResolution:
    def test_backfill_connects_to_company_suffixed_db_without_error(
        self, two_company_env, monkeypatch
    ):
        monkeypatch.setenv("TRACKER_COMPANY", "openai")
        module = _load_backfill_module()
        monkeypatch.setattr(module, "fetch_job_details_batch", lambda company, job_ids: [])

        result = module.main()

        assert result == 0
        # The correctly-suffixed DB should exist and be untouched/creatable;
        # a bogus plain tracker.db should never have been created by this run.
        assert (two_company_env / "tracker-openai.db").exists()
        assert not (two_company_env / "tracker.db").exists()

    def test_backfill_defaults_to_first_configured_company(self, two_company_env, monkeypatch):
        module = _load_backfill_module()
        seen_company = {}

        def fake_fetch(company, job_ids):
            seen_company["company"] = company
            return []

        monkeypatch.setattr(module, "fetch_job_details_batch", fake_fetch)

        result = module.main()

        assert result == 0
        assert seen_company["company"] == "anthropic"

    def test_backfill_parses_and_stores_compensation(self, two_company_env, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANY", "openai")
        module = _load_backfill_module()

        def fake_fetch(company, job_ids):
            return [
                {
                    "id": 2,
                    "content": "Salary: $120,000 - $150,000 annually",
                }
            ]

        monkeypatch.setattr(module, "fetch_job_details_batch", fake_fetch)

        result = module.main()

        assert result == 0
        conn = sqlite3.connect(str(two_company_env / "tracker-openai.db"))
        row = conn.execute(
            "SELECT job_id, salary_min, salary_max FROM compensation WHERE job_id = 2"
        ).fetchone()
        conn.close()
        assert row is not None
