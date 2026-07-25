from fastapi.testclient import TestClient

from ferminator.settings import get_settings
from ferminator.web import _failed_auth, app


def test_healthz():
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["demo_mode"] is True
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_readyz_reports_demo_readiness():
    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "demo"}


def test_request_id_is_sanitized():
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"x-request-id": "x" * 129})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "x" * 129


def test_today_renders_personal_briefing():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Good morning, Adam" in response.text
    assert "Director, AI Enablement" in response.text
    assert "clearly labeled sample opportunities" in response.text


def test_discover_defaults_to_controlled_review_tier():
    with TestClient(app) as client:
        response = client.get("/discover")

    assert response.status_code == 200
    assert "Worth reviewing (58%+)" in response.text
    assert "Every role passed" not in response.text


def test_discover_filters_results():
    with TestClient(app) as client:
        response = client.get("/discover", params={"q": "Notion", "min_score": 0})

    assert response.status_code == 200
    assert "Senior Manager, Knowledge Operations" in response.text
    assert "Director, AI Enablement" not in response.text


def test_all_primary_pages_render():
    with TestClient(app) as client:
        for path in ("/pipeline", "/companies", "/intelligence", "/profile"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "Ferminator" in response.text


def test_fit_lens_renders_explainable_components():
    with TestClient(app) as client:
        response = client.get("/fit/airtable-ai-enablement")

    assert response.status_code == 200
    assert "Why this is here" in response.text
    assert "Evidence match" in response.text
    assert "Listing facts" in response.text


def test_fit_lens_returns_404_for_unknown_job():
    with TestClient(app) as client:
        response = client.get("/fit/unknown")

    assert response.status_code == 404


def test_shared_password_failures_keep_security_headers(monkeypatch):
    monkeypatch.setenv("FERMINATOR_AUTH_MODE", "shared_password")
    monkeypatch.setenv("FERMINATOR_ALPHA_PASSWORD", "correct-horse")
    get_settings.cache_clear()
    _failed_auth.clear()
    try:
        with TestClient(app) as client:
            response = client.get("/")
    finally:
        get_settings.cache_clear()
        _failed_auth.clear()

    assert response.status_code == 401
    assert response.headers["x-request-id"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_shared_password_is_rate_limited(monkeypatch):
    monkeypatch.setenv("FERMINATOR_AUTH_MODE", "shared_password")
    monkeypatch.setenv("FERMINATOR_ALPHA_PASSWORD", "correct-horse")
    get_settings.cache_clear()
    _failed_auth.clear()
    try:
        with TestClient(app) as client:
            for _ in range(5):
                assert client.get("/").status_code == 401
            response = client.get("/")
    finally:
        get_settings.cache_clear()
        _failed_auth.clear()

    assert response.status_code == 429
    assert response.headers["retry-after"] == "300"
