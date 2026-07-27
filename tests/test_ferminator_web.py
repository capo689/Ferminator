import time
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

import ferminator.web as web
from ferminator import __version__
from ferminator.demo import scored_jobs
from ferminator.profiles import load_profile
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


def test_slow_dashboard_work_does_not_starve_health_check(monkeypatch):
    query_started = Event()
    release_query = Event()
    original_matches = web._matches

    def slow_matches(*args, **kwargs):
        query_started.set()
        assert release_query.wait(timeout=3)
        return original_matches(*args, **kwargs)

    monkeypatch.setattr(web, "_matches", slow_matches)
    with TestClient(app) as client:
        dashboard = Thread(target=lambda: client.get("/discover"))
        dashboard.start()
        assert query_started.wait(timeout=1)

        started = time.perf_counter()
        response = client.get("/healthz")
        duration = time.perf_counter() - started

        release_query.set()
        dashboard.join(timeout=3)

    assert response.status_code == 200
    assert duration < 1
    assert not dashboard.is_alive()


def test_request_id_is_sanitized():
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"x-request-id": "x" * 129})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "x" * 129


def test_today_renders_personal_briefing():
    with TestClient(app) as client:
        response = client.get(
            "/",
            headers={
                "host": "ferminator-web.onrender.com",
                "x-forwarded-proto": "http",
            },
        )

    assert response.status_code == 200
    assert "Good morning, Adam" in response.text
    assert "clearly labeled sample opportunities" in response.text
    assert 'href="/static/app.css' in response.text
    assert 'src="/static/app.js' in response.text
    assert "http://ferminator-web.onrender.com/static/" not in response.text
    assert "company-anthropic.svg" not in response.text


def test_discover_defaults_to_controlled_review_tier():
    with TestClient(app) as client:
        response = client.get("/discover")

    assert response.status_code == 200
    assert "Use role settings" in response.text
    assert "Every role passed" not in response.text


def test_discover_feedback_controls_include_duplicate_and_undo() -> None:
    template = Path("src/ferminator/templates/discover.html").read_text(encoding="utf-8")
    script = Path("src/ferminator/static/app.js").read_text(encoding="utf-8")

    assert '"duplicate"' in template
    assert "Undo rating" in template
    assert "Why is this match wrong?" in template
    assert 'name="wrong_reason_code"' in template
    assert "data-wrong-feedback" in template
    assert "show_rejected" in template
    assert "Show Wrong &amp; Duplicate" in template
    assert "event.preventDefault()" in script
    assert "event.stopPropagation()" in script
    assert "window.setTimeout(() =>" in script


def test_wrong_feedback_export_is_downloadable_markdown() -> None:
    with TestClient(app) as client:
        response = client.get("/feedback/export.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in response.headers["content-disposition"]
    assert "# Ferminator Wrong-Match Calibration" in response.text


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
    assert "data-role-slider" in response.text
    assert "Advertising Copywriter" in response.text
    assert "Copywriting" in response.text
    assert "50%" in response.text
    assert f"/static/app.js?v={__version__}" in response.text


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


def test_fit_lens_converts_legacy_html_description_to_copyable_text(monkeypatch):
    settings = web.get_settings().model_copy(update={"demo_mode": False})
    monkeypatch.setattr(web, "get_settings", lambda: settings)
    matches = scored_jobs(load_profile(settings.profile_path))
    job_id = matches[0]["id"]

    class Repository:
        def web_matches(self, *_args, **_kwargs):
            return matches

        def job_description(self, *_args):
            return "<p>Lead <strong>AI adoption</strong>.</p><ul><li>Build tools</li></ul>"

        def pipeline(self, *_args):
            return {"stages": {}, "terminal": []}

        def close(self):
            pass

    monkeypatch.setattr(web, "_repository", Repository)
    response = TestClient(app).get(f"/fit/{job_id}")
    assert response.status_code == 200
    assert "Lead AI adoption" in response.text
    assert "Build tools" in response.text
    assert "&lt;p&gt;" not in response.text
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


def test_supabase_auth_redirects_anonymous_browser(monkeypatch) -> None:
    settings = web.get_settings().model_copy(
        update={
            "auth_mode": "supabase",
            "supabase_url": "https://example.supabase.co",
            "supabase_publishable_key": "sb_publishable_test",
        }
    )
    monkeypatch.setattr(web, "get_settings", lambda: settings)

    async def anonymous(_request, _client):
        return None

    monkeypatch.setattr(web, "current_user_id", anonymous)
    response = TestClient(app).get("/discover", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_supabase_user_cannot_open_admin_control_plane(monkeypatch) -> None:
    settings = web.get_settings().model_copy(
        update={
            "auth_mode": "supabase",
            "supabase_url": "https://example.supabase.co",
            "supabase_publishable_key": "sb_publishable_test",
        }
    )
    monkeypatch.setattr(web, "get_settings", lambda: settings)

    async def signed_in(_request, _client):
        return "user-id"

    class Repository:
        def account_for_user(self, _user_id):
            return SimpleNamespace(id="account-id", role="user", status="active")

        def close(self):
            pass

    monkeypatch.setattr(web, "current_user_id", signed_in)
    monkeypatch.setattr(web, "_repository", Repository)
    response = TestClient(app).get("/admin")
    assert response.status_code == 403


def _origin_request(origin: str | None, base_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        headers={"origin": origin} if origin else {},
        base_url=base_url,
    )


def test_same_origin_accepts_https_origin_behind_tls_proxy(monkeypatch):
    """Regression: behind Render's TLS-terminating proxy request.base_url is
    http:// while browsers send an https:// Origin. Comparing against
    base_url 403'd every mutation, which is what broke save-to-pipeline."""
    monkeypatch.setenv("FERMINATOR_ENV", "production")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://ferminator-web.onrender.com")
    get_settings.cache_clear()
    try:
        # The real browser case: proxy reports http, browser sends https.
        web._same_origin(
            _origin_request(
                "https://ferminator-web.onrender.com",
                "http://ferminator-web.onrender.com/",
            )
        )
        # No Origin header (same-origin form navigation) stays allowed.
        web._same_origin(_origin_request(None, "http://ferminator-web.onrender.com/"))
    finally:
        get_settings.cache_clear()


def test_same_origin_rejects_foreign_and_downgraded_origins(monkeypatch):
    monkeypatch.setenv("FERMINATOR_ENV", "production")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://ferminator-web.onrender.com")
    get_settings.cache_clear()
    try:
        for origin in (
            "https://evil.example",
            "http://ferminator-web.onrender.com",  # scheme downgrade
        ):
            try:
                web._same_origin(_origin_request(origin, "http://ferminator-web.onrender.com/"))
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError(f"expected 403 for origin {origin}")
    finally:
        get_settings.cache_clear()


def test_dockerfile_does_not_blanket_trust_forwarded_headers():
    """Regression: --forwarded-allow-ips=* makes uvicorn return the LEFTMOST
    X-Forwarded-For entry, which is client-supplied. That makes
    request.client.host attacker-controlled and defeats the login rate
    limiter in _auth_key. Trust must stay scoped to the proxy's own range."""
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "--proxy-headers" in dockerfile, "proxy headers are load-bearing for the https scheme"
    assert "--forwarded-allow-ips=*" not in dockerfile
    assert '"--forwarded-allow-ips=*"' not in dockerfile


def test_scoped_forwarded_trust_resolves_the_real_client():
    """With trust scoped to RFC1918, uvicorn walks X-Forwarded-For in reverse
    and returns the first untrusted host (the real client) rather than the
    attacker-supplied leftmost entry."""
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    scoped = _TrustedHosts("10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1")
    spoofed_then_real = "203.0.113.99, 198.51.100.7"

    host, _ = scoped.get_trusted_client_address(spoofed_then_real)
    assert host == "198.51.100.7", "must ignore the client-supplied leftmost entry"

    # The proxy's own peer address must stay trusted, or X-Forwarded-Proto
    # stops being applied and request.base_url regresses to http://.
    assert "10.238.20.14" in scoped

    blanket = _TrustedHosts("*")
    assert blanket.get_trusted_client_address(spoofed_then_real)[0] == "203.0.113.99"
