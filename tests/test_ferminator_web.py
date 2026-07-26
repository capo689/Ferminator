from fastapi.testclient import TestClient

from ferminator.settings import get_settings
from ferminator.web import _apply_visible_compensation, _failed_auth, app


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
    assert "clearly labeled sample opportunities" in response.text


def test_discover_defaults_to_controlled_review_tier():
    with TestClient(app) as client:
        response = client.get("/discover")

    assert response.status_code == 200
    assert "Use role settings" in response.text
    assert "Every role passed" not in response.text


def test_discover_filters_results():
    with TestClient(app) as client:
        response = client.get("/discover", params={"q": "Notion", "min_score": 0})

    assert response.status_code == 200
    assert "Director, AI Enablement" not in response.text


def test_description_compensation_is_added_only_to_visible_result() -> None:
    visible = _apply_visible_compensation(
        {
            "compensation": None,
            "compensation_source": None,
            "compensation_text": "The annual base salary range is $175,000–$215,000.",
            "concerns": [
                "Compensation is not disclosed.",
                "Confirm travel expectations.",
            ],
        }
    )

    assert visible["compensation"] == "$175K–$215K"
    assert visible["compensation_source"] == "description"
    assert visible["concerns"] == ["Confirm travel expectations."]
    assert "compensation_text" not in visible


def test_profile_renders_role_threshold_control_and_copy_family():
    with TestClient(app) as client:
        response = client.get("/profile")

    assert response.status_code == 200
    assert 'data-role-slider' in response.text
    assert "Advertising Copywriter" in response.text
    assert "Copywriting" in response.text
    assert "65%" in response.text
    assert "/static/app.js?v=0.6.3" in response.text


def test_demo_role_threshold_update_redirects_without_mutation():
    with TestClient(app) as client:
        response = client.post(
            "/profile/role-threshold/copywriting/30",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/profile?family=copywriting"


def test_all_primary_pages_render():
    with TestClient(app) as client:
        for path in ("/pipeline", "/companies", "/intelligence", "/profile"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "Ferminator" in response.text


def test_pipeline_exposes_reversible_movement_and_campaign_controls():
    with TestClient(app) as client:
        response = client.get("/pipeline")

    assert response.status_code == 200
    assert "data-pipeline-board" in response.text
    assert "data-pipeline-search" in response.text
    assert "data-move-select" in response.text
    assert "Unsave" in response.text
    assert "Archive" in response.text
    assert "Close with outcome" in response.text
    assert "Follow-up" in response.text


def test_intelligence_uses_calculated_snapshot_not_fake_thirty_day_claims():
    with TestClient(app) as client:
        response = client.get("/intelligence")

    assert response.status_code == 200
    assert "Your market, translated into decisions." in response.text
    assert "Building an honest trend baseline" in response.text
    assert "Compared with the previous 30 days" not in response.text
    assert "AI enablement roles" not in response.text
    assert "No invented trends." in response.text


def test_company_directory_renders_search_health_and_sources():
    with TestClient(app) as client:
        response = client.get("/companies")

    assert response.status_code == 200
    assert 'id="company-search"' in response.text
    assert "Greenhouse · airtable" in response.text
    assert "Healthy" in response.text
    assert "Open board" in response.text


def test_fit_lens_renders_explainable_components():
    with TestClient(app) as client:
        response = client.get("/fit/airtable-ai-enablement")

    assert response.status_code == 200
    assert "Why this is here" in response.text
    assert "Evidence match" in response.text
    assert "Listing facts" in response.text
    assert "Complete job description" in response.text
    assert "Copy complete JD" in response.text


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
