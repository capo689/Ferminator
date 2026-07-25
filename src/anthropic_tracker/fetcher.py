"""Greenhouse API client for fetching job data."""

import time

import httpx

from anthropic_tracker.config import (
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF,
    SALARY_FETCH_DELAY,
    USER_AGENT,
)

GREENHOUSE_BOARDS_HOST = "https://boards-api.greenhouse.io/v1/boards"


def board_url(company: str) -> str:
    return f"{GREENHOUSE_BOARDS_HOST}/{company}/jobs"


def departments_url(company: str) -> str:
    return f"{GREENHOUSE_BOARDS_HOST}/{company}/departments"


def offices_url(company: str) -> str:
    return f"{GREENHOUSE_BOARDS_HOST}/{company}/offices"


def _get_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )


def _request_with_retry(client: httpx.Client, url: str) -> dict:
    """GET a URL with exponential backoff retries."""
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2**attempt))
    raise last_exc  # type: ignore[misc]


def fetch_jobs(company: str, content: bool = False) -> list[dict]:
    """Fetch all open jobs from the Greenhouse API.

    Args:
        company: Greenhouse board slug (e.g. "anthropic").
        content: If True, include HTML job descriptions (slower, one request).
    """
    url = board_url(company)
    if content:
        url += "?content=true"
    with _get_client() as client:
        data = _request_with_retry(client, url)
    return data.get("jobs", [])


def fetch_departments(company: str) -> list[dict]:
    """Fetch all departments from the Greenhouse API."""
    with _get_client() as client:
        data = _request_with_retry(client, departments_url(company))
    return data.get("departments", [])


def fetch_offices(company: str) -> list[dict]:
    """Fetch all offices from the Greenhouse API."""
    with _get_client() as client:
        data = _request_with_retry(client, offices_url(company))
    return data.get("offices", [])


def build_department_map(departments: list[dict]) -> dict[int, dict]:
    """Build a mapping from job_id to department info.

    The Greenhouse departments endpoint nests jobs inside each department.
    The base /jobs endpoint does NOT include department data.
    """
    job_to_dept: dict[int, dict] = {}
    for dept in departments:
        dept_info = {"id": dept["id"], "name": dept["name"]}
        for job in dept.get("jobs", []):
            job_to_dept[job["id"]] = dept_info
    return job_to_dept


def enrich_jobs_with_departments(
    jobs: list[dict], dept_map: dict[int, dict]
) -> list[dict]:
    """Add department data to job dicts that lack it."""
    for job in jobs:
        if not job.get("departments"):
            dept = dept_map.get(job["id"])
            if dept:
                job["departments"] = [
                    {"id": dept["id"], "name": dept["name"],
                     "child_ids": [], "parent_id": None}
                ]
    return jobs


def fetch_job_detail(company: str, job_id: int) -> dict:
    """Fetch a single job with full HTML content for salary parsing."""
    url = f"{board_url(company)}/{job_id}"
    with _get_client() as client:
        return _request_with_retry(client, url)


def fetch_job_details_batch(company: str, job_ids: list[int]) -> list[dict]:
    """Fetch multiple job details with polite throttling.

    Returns list of job detail dicts. Skips jobs that fail after retries.
    """
    results = []
    with _get_client() as client:
        for i, job_id in enumerate(job_ids):
            try:
                url = f"{board_url(company)}/{job_id}"
                detail = _request_with_retry(client, url)
                results.append(detail)
            except (httpx.HTTPStatusError, httpx.TransportError):
                pass  # skip failed jobs, don't block the batch
            if i < len(job_ids) - 1:
                time.sleep(SALARY_FETCH_DELAY)
    return results
