"""Tests for the FastAPI web dashboard's per-company routing."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from anthropic_tracker.db import init_db
from anthropic_tracker.web import app


def _seed(db_path, total_active_jobs):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """INSERT INTO daily_snapshots
           (date, total_active_jobs, jobs_added, jobs_removed)
           VALUES ('2026-07-22', ?, 0, 0)""",
        (total_active_jobs,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def two_company_env(tmp_path, monkeypatch):
    """Seed separate DBs for two companies and point config at them."""
    monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
    monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
    _seed(tmp_path / "tracker-anthropic.db", total_active_jobs=111)
    _seed(tmp_path / "tracker-openai.db", total_active_jobs=222)
    return tmp_path


class TestCompanyRouting:
    def test_api_summary_defaults_to_first_configured_company(self, two_company_env):
        with TestClient(app) as client:
            resp = client.get("/api/summary")
        assert resp.json()["total"] == 111

    def test_api_summary_honors_x_company_header(self, two_company_env):
        with TestClient(app) as client:
            resp = client.get("/api/summary", headers={"X-Company": "openai"})
        assert resp.json()["total"] == 222

    def test_dashboard_page_honors_company_query_param(self, two_company_env):
        with TestClient(app) as client:
            resp = client.get("/?company=openai")
        assert resp.status_code == 200
        assert "openai" in resp.text.lower()

    def test_partial_summary_honors_x_company_header(self, two_company_env):
        with TestClient(app) as client:
            resp = client.get("/partials/summary", headers={"X-Company": "openai"})
        assert resp.status_code == 200
        assert "222" in resp.text

    def test_unrecognized_company_slug_returns_empty_instead_of_500(self, two_company_env):
        with TestClient(app) as client:
            resp = client.get("/api/summary", headers={"X-Company": "totally-unknown-slug"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_malicious_x_company_header_returns_400(self, two_company_env):
        with TestClient(app) as client:
            resp = client.get("/api/summary", headers={"X-Company": "../../etc/passwd"})
        assert resp.status_code == 400
