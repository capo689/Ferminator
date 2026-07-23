"""Tests for the Greenhouse API fetcher."""

import httpx
import pytest
import respx

from anthropic_tracker.fetcher import board_url, fetch_jobs

MOCK_RESPONSE = {
    "jobs": [
        {
            "id": 1001,
            "title": "Test Job",
            "location": {"name": "San Francisco, CA"},
            "departments": [{"id": 100, "name": "Engineering"}],
            "offices": [],
        }
    ]
}


class TestFetchJobs:
    @respx.mock
    def test_fetch_returns_jobs(self):
        respx.get(board_url("anthropic")).mock(
            return_value=httpx.Response(200, json=MOCK_RESPONSE)
        )
        jobs = fetch_jobs("anthropic")
        assert len(jobs) == 1
        assert jobs[0]["id"] == 1001

    @respx.mock
    def test_fetch_with_content_flag(self):
        respx.get(board_url("anthropic") + "?content=true").mock(
            return_value=httpx.Response(200, json=MOCK_RESPONSE)
        )
        jobs = fetch_jobs("anthropic", content=True)
        assert len(jobs) == 1

    @respx.mock
    def test_fetch_handles_empty_response(self):
        respx.get(board_url("anthropic")).mock(
            return_value=httpx.Response(200, json={"jobs": []})
        )
        jobs = fetch_jobs("anthropic")
        assert jobs == []

    @respx.mock
    def test_fetch_retries_on_server_error(self):
        route = respx.get(board_url("anthropic"))
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, json=MOCK_RESPONSE),
        ]
        jobs = fetch_jobs("anthropic")
        assert len(jobs) == 1

    @respx.mock
    def test_fetch_raises_after_retries_exhausted(self):
        respx.get(board_url("anthropic")).mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(httpx.HTTPStatusError):
            fetch_jobs("anthropic")


class TestBoardUrlBuildsFromSlug:
    def test_different_companies_get_different_urls(self):
        assert board_url("anthropic") != board_url("openai")
        assert "anthropic" in board_url("anthropic")
        assert "openai" in board_url("openai")

    @respx.mock
    def test_fetch_jobs_uses_the_given_company_slug(self):
        respx.get(board_url("openai")).mock(
            return_value=httpx.Response(200, json=MOCK_RESPONSE)
        )
        jobs = fetch_jobs("openai")
        assert len(jobs) == 1
