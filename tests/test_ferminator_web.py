from fastapi.testclient import TestClient

from ferminator.web import app


def test_healthz():
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["demo_mode"] is True


def test_today_renders_personal_briefing():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Good morning, Adam" in response.text
    assert "Director, AI Enablement" in response.text
    assert "clearly labeled sample opportunities" in response.text


def test_discover_filters_results():
    with TestClient(app) as client:
        response = client.get("/discover", params={"q": "Notion", "min_score": 60})

    assert response.status_code == 200
    assert "Senior Manager, Knowledge Operations" in response.text
    assert "Director, AI Enablement" not in response.text


def test_all_primary_pages_render():
    with TestClient(app) as client:
        for path in ("/pipeline", "/companies", "/intelligence", "/profile"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "Ferminator" in response.text

