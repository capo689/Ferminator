from ferminator.display_score import calibrate_display_score, match_display
from ferminator.geography import (
    coordinates_for_label,
    distance_miles,
    lookup_zip,
)


def test_display_calibration_matches_product_bands_and_preserves_order() -> None:
    raw_scores = [0, 30, 51, 52, 59, 60, 67, 68, 74, 75, 90, 100]
    shown = [calibrate_display_score(score) for score in raw_scores]

    assert shown == sorted(shown)
    assert calibrate_display_score(52) == 68
    assert calibrate_display_score(60) == 78
    assert calibrate_display_score(68) == 85
    assert calibrate_display_score(75) == 91
    assert calibrate_display_score(100) == 96
    assert match_display(75).label == "Exceptional"


def test_offline_postal_lookup_resolves_zip_and_city_state() -> None:
    bend = lookup_zip("97702")
    city = coordinates_for_label("Bend, OR, United States")

    assert bend is not None
    assert city is not None
    assert city.state == "OR"
    assert distance_miles(bend, city) < 20


def test_discover_renders_bookmarkable_controls_and_calibrated_scores() -> None:
    from fastapi.testclient import TestClient

    from ferminator.web import app

    with TestClient(app) as client:
        response = client.get(
            "/discover",
            params={
                "posted": "7d",
                "location_mode": "remote_or_near",
                "zip": "97702",
                "radius": 50,
                "sort": "relevance",
            },
        )

    assert response.status_code == 200
    assert 'name="posted"' in response.text
    assert 'name="location_mode"' in response.text
    assert 'name="zip"' in response.text
    assert "Last 7 days ×" in response.text
    assert "Internal relevance:" in response.text or "No opportunities" in response.text


def test_discover_handles_unknown_zip_without_server_error() -> None:
    from fastapi.testclient import TestClient

    from ferminator.web import app

    with TestClient(app) as client:
        response = client.get(
            "/discover",
            params={"location_mode": "near", "zip": "00000", "radius": 50},
        )

    assert response.status_code == 200
    assert "Enter a valid five-digit US ZIP code" in response.text
