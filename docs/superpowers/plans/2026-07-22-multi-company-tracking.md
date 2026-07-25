# Multi-company Greenhouse Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the tracker follow several companies' Greenhouse job boards at once, each with its own history/deltas/alerts, via a new `TRACKER_COMPANIES` env var — with zero database schema changes.

**Architecture:** One SQLite file per company (`tracker-{slug}.db`), selected at read/write time by a `company` slug threaded through the CLI (`--company` flag, default = all configured companies for `fetch`) and the web app (`X-Company` header for htmx partials/API, `?company=` query param for the page). Single-company installs keep today's exact filename (`tracker.db`) and behavior — this is purely additive.

**Tech Stack:** Python 3.11+, Click, FastAPI + Jinja2 + htmx, SQLite, httpx, pytest + respx.

## Global Constraints

- `TRACKER_COMPANIES` is comma-separated Greenhouse board slugs; parsing strips whitespace, lowercases, drops empties, and dedupes while preserving order. Unset → `["anthropic"]`.
- `get_db_path`: explicit `--db`/`db_path` always wins outright, regardless of company count. One configured company → today's filename unchanged. Multiple → `tracker-{slug}.db`.
- No schema changes anywhere (`db.py` untouched). No cross-company aggregation view. No DB-backed company registry — the list is static config, read fresh from the env var on every call.
- Company slugs are never validated against the configured list, in the CLI or the web app — an unrecognized slug just resolves to its own (possibly empty) auto-created DB file.
- Docker Compose: no structural changes — same volume, same services, one new env var in the shared `x-image` anchor.

---

## File Structure

**Modified:**
- `src/anthropic_tracker/config.py` — add `get_companies()`, extend `get_db_path()` with a `company` param, drop the `GREENHOUSE_*` URL constants.
- `src/anthropic_tracker/fetcher.py` — add `board_url()`/`departments_url()`/`offices_url()` slug-based URL builders; every fetch function takes a `company` argument.
- `src/anthropic_tracker/cli.py` — group gains `--company`; `fetch`'s body is extracted into `_fetch_one()` so it can loop over every configured company by default.
- `src/anthropic_tracker/web.py` — `lifespan` initializes every configured company's DB; every route resolves `company` from a header/query param instead of a fixed path.
- `src/anthropic_tracker/templates/base.html` — `hx-headers` on `<body>` so htmx requests inherit the current company; a company-tabs nav in the header.
- `src/anthropic_tracker/static/style.css` — lay out `.header-left` as a flex row; style `.company-tabs`/`.company-tab`/`.company-tab.active`.
- `docker-compose.yml` — one new env var in the shared `x-image` anchor.
- `README.md` — document `TRACKER_COMPANIES`, add the manual migration note, update the Configuration table.
- `tests/test_fetcher.py` — rewritten to use `board_url()` instead of the removed `GREENHOUSE_API_URL` constant, and to pass `company` into every fetch call.
- `tests/test_cli.py` — `_mock_api()` switches to `fetcher.board_url`/`departments_url`; three new tests for multi-company `fetch`.
- `tests/conftest.py` — add an autouse fixture clearing `TRACKER_COMPANIES`/`TRACKER_DB` so tests are hermetic against the host shell's environment.

**New:**
- `tests/test_config.py` — `get_companies()` parsing rules, `get_db_path()` resolution order.
- `tests/test_web.py` — `X-Company` header and `?company=` query param select the right DB file.

---

### Task 1: Config, fetcher, and CLI — multi-company core

This is one task, not three, because the pieces are load-bearing on each other: `fetcher.py`'s functions require a `company` argument the moment `config.py`'s fixed URL constants disappear, and `cli.py`'s `fetch` command breaks immediately unless it's updated in step with `fetcher.py`. Splitting these into separate tasks would leave an intermediate state where the test suite can't pass. Within the task, commit after each file lands so history stays granular.

**Files:**
- Modify: `src/anthropic_tracker/config.py`
- Modify: `src/anthropic_tracker/fetcher.py`
- Modify: `src/anthropic_tracker/cli.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_fetcher.py`
- Modify: `tests/test_cli.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `get_companies() -> list[str]`, `get_db_path(db_path: str | None = None, company: str | None = None) -> Path`, `board_url(company: str) -> str`, `departments_url(company: str) -> str`, `offices_url(company: str) -> str`, `fetch_jobs(company: str, content: bool = False) -> list[dict]`, `fetch_departments(company: str) -> list[dict]`, `fetch_offices(company: str) -> list[dict]`, `fetch_job_detail(company: str, job_id: int) -> dict`, `fetch_job_details_batch(company: str, job_ids: list[int]) -> list[dict]`. These are consumed by Task 2 (`web.py`) and are the CLI/fetch layer's public surface.

- [ ] **Step 1: Write the failing test for company-list parsing and DB path resolution**

Create `tests/test_config.py`:

```python
"""Tests for config resolution: company list parsing and DB path."""

from pathlib import Path

from anthropic_tracker.config import get_companies, get_db_path


class TestGetCompanies:
    def test_defaults_to_anthropic(self):
        assert get_companies() == ["anthropic"]

    def test_parses_comma_separated_list(self, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai,notion")
        assert get_companies() == ["anthropic", "openai", "notion"]

    def test_strips_whitespace_and_lowercases(self, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", " Anthropic , OpenAI ")
        assert get_companies() == ["anthropic", "openai"]

    def test_drops_empty_entries_and_dedupes(self, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,,anthropic,openai")
        assert get_companies() == ["anthropic", "openai"]


class TestGetDbPath:
    def test_explicit_db_path_wins_outright(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        explicit = str(tmp_path / "custom.db")
        assert get_db_path(explicit, "openai") == Path(explicit)

    def test_single_company_uses_plain_filename(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path() == tmp_path / "tracker.db"

    def test_multiple_companies_suffix_by_slug(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path(company="openai") == tmp_path / "tracker-openai.db"
        assert get_db_path(company="anthropic") == tmp_path / "tracker-anthropic.db"

    def test_multiple_companies_default_to_first_when_unspecified(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACKER_COMPANIES", "openai,anthropic")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        assert get_db_path() == tmp_path / "tracker-openai.db"
```

Also modify `tests/conftest.py` to add an autouse fixture — without it, a developer's shell exporting `TRACKER_COMPANIES` would silently change these tests' behavior:

```python
"""Shared pytest fixtures."""

import copy
import sqlite3

import pytest

from anthropic_tracker.db import init_db

from .fixtures import SAMPLE_JOBS


@pytest.fixture(autouse=True)
def _clean_tracker_env(monkeypatch):
    """Isolate tests from TRACKER_* env vars set in the host shell."""
    monkeypatch.delenv("TRACKER_COMPANIES", raising=False)
    monkeypatch.delenv("TRACKER_DB", raising=False)


@pytest.fixture
def db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_jobs():
    """Return a copy of the sample jobs list."""
    return copy.deepcopy(SAMPLE_JOBS)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_companies' from 'anthropic_tracker.config'`

- [ ] **Step 3: Implement `get_companies()` and extend `get_db_path()`**

Replace `src/anthropic_tracker/config.py` in full:

```python
"""Configuration constants and paths."""

import os
from pathlib import Path

# HTTP settings
USER_AGENT = "anthropic-tracker/0.1.0 (hiring metrics tracker)"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2
RETRY_BACKOFF = 1.0  # seconds, doubled each retry
SALARY_FETCH_DELAY = 0.5  # seconds between individual job fetches

# Data storage
DEFAULT_DATA_DIR = Path.home() / ".anthropic-tracker"
DB_FILENAME = "tracker.db"

# Alert thresholds
FREEZE_THRESHOLD_PCT = 20  # total roles drop >20% = possible hiring freeze
SURGE_THRESHOLD_PCT = 50  # department grows >50% in a week
MASS_REMOVAL_THRESHOLD = 30  # >30 roles removed in a single day
SALARY_SHIFT_THRESHOLD_PCT = 10  # median salary changes >10%

# Schema version
CURRENT_SCHEMA_VERSION = 1

DEFAULT_COMPANIES = ["anthropic"]


def get_companies() -> list[str]:
    """Parse TRACKER_COMPANIES into a deduped list of Greenhouse slugs."""
    raw = os.environ.get("TRACKER_COMPANIES", "")
    seen = set()
    companies = []
    for part in raw.split(","):
        slug = part.strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            companies.append(slug)
    return companies or list(DEFAULT_COMPANIES)


def get_db_path(db_path: str | None = None, company: str | None = None) -> Path:
    """Resolve database file path.

    --db/db_path always wins. Otherwise: one configured company keeps
    today's filename; multiple companies suffix by slug.
    """
    if db_path:
        return Path(db_path)

    companies = get_companies()
    slug = company or companies[0]

    env_path = os.environ.get("TRACKER_DB")
    if env_path:
        base = Path(env_path)
        base.parent.mkdir(parents=True, exist_ok=True)
        if len(companies) == 1:
            return base
        return base.parent / f"{base.stem}-{slug}{base.suffix}"

    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if len(companies) == 1:
        return DEFAULT_DATA_DIR / DB_FILENAME
    stem = Path(DB_FILENAME).stem
    suffix = Path(DB_FILENAME).suffix
    return DEFAULT_DATA_DIR / f"{stem}-{slug}{suffix}"
```

Note: `GREENHOUSE_API_URL`, `GREENHOUSE_CONTENT_URL`, `GREENHOUSE_DEPARTMENTS_URL`, and `GREENHOUSE_OFFICES_URL` are deliberately gone — they move into `fetcher.py` as slug-based functions in Step 6.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/anthropic_tracker/config.py tests/test_config.py tests/conftest.py
git commit -m "feat: parse TRACKER_COMPANIES and suffix DB path by company slug"
```

- [ ] **Step 6: Write the failing test for slug-based fetcher URLs**

Replace `tests/test_fetcher.py` in full:

```python
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
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `pytest tests/test_fetcher.py -v`
Expected: FAIL — `ImportError: cannot import name 'board_url' from 'anthropic_tracker.fetcher'` (the module itself also fails to import, since it still references the now-removed `GREENHOUSE_*` constants from `config.py`)

- [ ] **Step 8: Implement slug-based URL functions and thread `company` through every fetch call**

Replace `src/anthropic_tracker/fetcher.py` in full:

```python
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
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `pytest tests/test_fetcher.py -v`
Expected: PASS (7 tests)

- [ ] **Step 10: Commit**

```bash
git add src/anthropic_tracker/fetcher.py tests/test_fetcher.py
git commit -m "feat: build Greenhouse URLs from a company slug instead of a fixed constant"
```

- [ ] **Step 11: Write the failing tests for multi-company CLI fetch**

Replace the top of `tests/test_cli.py` (imports and `_mock_api`) — everything from the file's start through `_mock_api`'s closing line:

```python
"""Tests for CLI commands."""

import json

import httpx
import respx
from click.testing import CliRunner

from anthropic_tracker.cli import cli
from anthropic_tracker.fetcher import board_url, departments_url
from tests.fixtures import SAMPLE_JOBS

MOCK_DEPARTMENTS = {
    "departments": [
        {
            "id": 100,
            "name": "Software Engineering (Infrastructure)",
            "jobs": [
                {"id": 1001, "title": "Senior Software Engineer, Infrastructure"},
                {"id": 1004, "title": "Forward Deployed Engineer"},
            ],
        },
        {
            "id": 200,
            "name": "Sales",
            "jobs": [
                {"id": 1002, "title": "Account Executive, Higher Education"},
                {"id": 1005, "title": "Solutions Architect, EMEA"},
            ],
        },
        {
            "id": 300,
            "name": "AI Research & Engineering",
            "jobs": [
                {"id": 1003, "title": "Research Scientist, Interpretability"},
            ],
        },
    ]
}


def _mock_api(company="anthropic"):
    """Set up standard API mocks for jobs + departments."""
    respx.get(board_url(company)).mock(
        return_value=httpx.Response(200, json={"jobs": SAMPLE_JOBS})
    )
    respx.get(departments_url(company)).mock(
        return_value=httpx.Response(200, json=MOCK_DEPARTMENTS)
    )
```

Leave the rest of the file (the `TestCLI` class and all its existing methods) untouched, and append a new class after it:

```python
class TestMultiCompanyFetch:
    @respx.mock
    def test_fetch_all_configured_companies_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        _mock_api("anthropic")
        _mock_api("openai")

        runner = CliRunner()
        result = runner.invoke(cli, ["fetch"])
        assert result.exit_code == 0
        assert (tmp_path / "tracker-anthropic.db").exists()
        assert (tmp_path / "tracker-openai.db").exists()

    @respx.mock
    def test_fetch_company_flag_scopes_to_one_company(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        _mock_api("openai")

        runner = CliRunner()
        result = runner.invoke(cli, ["fetch", "--company", "openai"])
        assert result.exit_code == 0
        assert (tmp_path / "tracker-openai.db").exists()
        assert not (tmp_path / "tracker-anthropic.db").exists()

    @respx.mock
    def test_fetch_continues_after_one_company_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        respx.get(board_url("anthropic")).mock(return_value=httpx.Response(500))
        _mock_api("openai")

        runner = CliRunner()
        result = runner.invoke(cli, ["fetch"])
        assert result.exit_code == 1
        assert (tmp_path / "tracker-openai.db").exists()
```

- [ ] **Step 12: Run the tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — the existing `test_fetch_command` and everything downstream of it errors with `TypeError: fetch_jobs() missing 1 required positional argument: 'company'` (cli.py still calls `fetch_jobs()` with no args); the three new `TestMultiCompanyFetch` tests fail because `fetch` doesn't accept `--company` or loop over configured companies yet.

- [ ] **Step 13: Implement `--company` and the multi-company fetch loop**

Replace `src/anthropic_tracker/cli.py` in full:

```python
"""CLI entry point for the Anthropic Hiring Tracker."""

import json
import sys

import click
from rich.console import Console

from anthropic_tracker.alerts import evaluate_alerts, show_alerts
from anthropic_tracker.config import get_companies, get_db_path
from anthropic_tracker.dashboard import show_dashboard
from anthropic_tracker.db import get_connection, init_db
from anthropic_tracker.delta import compute_delta
from anthropic_tracker.fetcher import (
    build_department_map,
    enrich_jobs_with_departments,
    fetch_departments,
    fetch_job_details_batch,
    fetch_jobs,
)
from anthropic_tracker.parser import parse_compensation
from anthropic_tracker.summarizer import (
    compensation_report,
    daily_summary,
    delta_summary,
    department_breakdown,
    format_report_csv,
    format_report_json,
    trends_report,
)

console = Console()


@click.group()
@click.option("--db", default=None, help="Path to SQLite database file")
@click.option("--company", default=None,
              help="Greenhouse company slug (default: first in TRACKER_COMPANIES)")
@click.pass_context
def cli(ctx, db, company):
    """Anthropic Hiring Tracker: monitor job openings via the Greenhouse API."""
    ctx.ensure_object(dict)
    companies = get_companies()
    ctx.obj["companies"] = companies
    ctx.obj["company"] = company or companies[0]
    ctx.obj["db_flag"] = db
    ctx.obj["db_path"] = str(get_db_path(db, ctx.obj["company"]))


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize the database."""
    db_path = ctx.obj["db_path"]
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()
    console.print(f"[green]Database initialized at {db_path}[/green]")


def _fetch_one(company: str, db_path: str, with_salary: bool) -> bool:
    """Fetch, compute deltas, and evaluate alerts for a single company.

    Returns False (after printing the error) on fetch failure, so a
    multi-company loop can keep going instead of aborting.
    """
    conn = get_connection(db_path)
    init_db(conn)

    console.print(f"[dim]Fetching jobs and departments for '{company}'...[/dim]")
    try:
        jobs = fetch_jobs(company)
        depts = fetch_departments(company)
        dept_map = build_department_map(depts)
        jobs = enrich_jobs_with_departments(jobs, dept_map)
    except Exception as exc:
        console.print(f"[red]Failed to fetch jobs for '{company}': {exc}[/red]")
        conn.close()
        return False

    console.print(f"[dim]Got {len(jobs)} jobs for '{company}'. Computing delta...[/dim]")
    result = compute_delta(conn, jobs)

    delta_summary(result.added, result.removed, result.total)

    if with_salary and result.added:
        new_ids = [j["id"] for j in result.added]
        console.print(f"[dim]Fetching salary data for {len(new_ids)} new jobs...[/dim]")
        details = fetch_job_details_batch(company, new_ids)
        salary_count = 0
        for detail in details:
            content = detail.get("content", "")
            if not content:
                continue
            comp = parse_compensation(content)
            if comp:
                conn.execute(
                    """INSERT OR REPLACE INTO compensation
                       (job_id, salary_min, salary_max, currency, comp_type, raw_text)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        detail["id"],
                        comp["salary_min"],
                        comp["salary_max"],
                        comp["currency"],
                        comp["comp_type"],
                        comp["raw_text"],
                    ),
                )
                salary_count += 1
        conn.commit()
        console.print(f"[dim]Parsed salary data for {salary_count}/{len(new_ids)} jobs.[/dim]")

    alerts = evaluate_alerts(conn, result)
    if alerts:
        console.print()
        for alert in alerts:
            color = {"info": "blue", "warning": "yellow", "critical": "red"}.get(
                alert.severity, "white"
            )
            console.print(f"[{color}][ALERT] {alert.message}[/{color}]")

    conn.close()
    return True


@cli.command()
@click.option("--with-salary", is_flag=True, help="Fetch content for salary parsing (slower)")
@click.option("--company", default=None,
              help="Fetch only this company (default: all configured companies)")
@click.pass_context
def fetch(ctx, with_salary, company):
    """Fetch current jobs from Greenhouse API and compute deltas."""
    targets = [company] if company else ctx.obj["companies"]

    all_ok = True
    for i, slug in enumerate(targets):
        db_path = str(get_db_path(ctx.obj["db_flag"], slug))
        all_ok = _fetch_one(slug, db_path, with_salary) and all_ok
        if i < len(targets) - 1:
            console.print()

    if not all_ok:
        sys.exit(1)


@cli.command()
@click.option("--date", default=None, help="Date to summarize (YYYY-MM-DD, default: latest)")
@click.pass_context
def summary(ctx, date):
    """Show summary for a specific date."""
    conn = get_connection(ctx.obj["db_path"])
    daily_summary(conn, date)
    conn.close()


@cli.command()
@click.option(
    "--format", "fmt",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format",
)
@click.pass_context
def report(ctx, fmt):
    """Generate a full report of current state."""
    conn = get_connection(ctx.obj["db_path"])

    if fmt == "json":
        data = format_report_json(conn)
        click.echo(json.dumps(data, indent=2, default=str))
    elif fmt == "csv":
        click.echo(format_report_csv(conn))
    else:
        department_breakdown(conn)
        console.print()
        compensation_report(conn)

    conn.close()


@cli.command()
@click.option("--days", default=30, help="Number of days to show")
@click.pass_context
def trends(ctx, days):
    """Show hiring trends over time."""
    conn = get_connection(ctx.obj["db_path"])
    trends_report(conn, days)
    conn.close()


@cli.command()
@click.pass_context
def dashboard(ctx):
    """Launch terminal dashboard."""
    conn = get_connection(ctx.obj["db_path"])
    show_dashboard(conn)
    conn.close()


@cli.command()
@click.option("--all", "show_all", is_flag=True, help="Show all alerts including acknowledged")
@click.pass_context
def alerts(ctx, show_all):
    """Show active alerts."""
    conn = get_connection(ctx.obj["db_path"])
    show_alerts(conn, unacked_only=not show_all)
    conn.close()
```

- [ ] **Step 14: Run the tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (12 tests — the original 8 plus the 3 new `TestMultiCompanyFetch` tests plus `test_init_command`)

- [ ] **Step 15: Commit**

```bash
git add src/anthropic_tracker/cli.py tests/test_cli.py
git commit -m "feat: loop CLI fetch over every configured company by default"
```

- [ ] **Step 16: Run the full suite to confirm nothing else regressed**

Run: `pytest -v`
Expected: PASS (all tests, including `test_alerts.py`, `test_db.py`, `test_delta.py`, `test_parser.py`, which don't touch config/fetcher/cli and should be unaffected)

---

### Task 2: Web dashboard company routing

**Files:**
- Modify: `src/anthropic_tracker/web.py`
- Modify: `src/anthropic_tracker/templates/base.html`
- Modify: `src/anthropic_tracker/static/style.css`
- Create: `tests/test_web.py`

**Interfaces:**
- Consumes: `get_companies() -> list[str]`, `get_db_path(db_path=None, company=None) -> Path` from Task 1's `config.py` (unchanged signatures).
- Produces: no new public functions consumed elsewhere — this task's deliverable is the running web app.

- [ ] **Step 1: Write the failing tests for company-aware routing**

Create `tests/test_web.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_web.py -v`
Expected: FAIL — `test_api_summary_honors_x_company_header` and `test_partial_summary_honors_x_company_header` get 111 instead of 222 (the `X-Company` header is ignored); `test_dashboard_page_honors_company_query_param` fails the `"openai" in resp.text.lower()` assertion (no company tabs exist yet).

- [ ] **Step 3: Implement per-route company resolution in `web.py`**

Replace `src/anthropic_tracker/web.py` in full:

```python
"""FastAPI web dashboard for the Anthropic Hiring Tracker."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from anthropic_tracker.config import get_companies, get_db_path
from anthropic_tracker.db import get_connection, init_db

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

X_COMPANY_HEADER = Header(default=None, alias="X-Company")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize schema once per configured company at startup. Each
    # request opens its own short-lived connection (sqlite is
    # process-shared via WAL).
    for slug in get_companies():
        conn = get_connection(str(get_db_path(None, slug)))
        try:
            init_db(conn)
        finally:
            conn.close()
    yield


app = FastAPI(title="Anthropic Hiring Tracker", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _db(company: str | None = None):
    """Open a fresh sqlite connection for the given company (or the default)."""
    slug = company or get_companies()[0]
    return get_connection(str(get_db_path(None, slug)))


def _escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards so user input doesn't act as a pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Pages ---


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, company: str | None = Query(default=None)):
    companies = get_companies()
    slug = company or companies[0]
    conn = _db(slug)
    try:
        snap = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        data = _build_dashboard_data(conn, snap)
        data["company"] = slug
        data["companies"] = companies
        return templates.TemplateResponse(request, "dashboard.html", context=data)
    finally:
        conn.close()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# --- API endpoints ---


@app.get("/api/summary")
async def api_summary(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        snap = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not snap:
            return {"total": 0, "added": 0, "removed": 0, "date": None}
        return {
            "total": snap["total_active_jobs"],
            "added": snap["jobs_added"],
            "removed": snap["jobs_removed"],
            "date": snap["date"],
        }
    finally:
        conn.close()


@app.get("/api/departments")
async def api_departments(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT d.name, COUNT(*) as cnt
               FROM jobs j JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               GROUP BY d.name ORDER BY cnt DESC"""
        ).fetchall()
        total = sum(r["cnt"] for r in rows)
        return {
            "departments": [
                {"name": r["name"], "count": r["cnt"],
                 "pct": round(r["cnt"] / total * 100, 1) if total else 0}
                for r in rows
            ],
            "total": total,
        }
    finally:
        conn.close()


@app.get("/api/locations")
async def api_locations(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT location_name, COUNT(*) as cnt
               FROM job_locations jl JOIN jobs j ON jl.job_id = j.id
               WHERE j.is_active = 1
               GROUP BY location_name ORDER BY cnt DESC"""
        ).fetchall()
        return {
            "locations": [
                {"name": r["location_name"], "count": r["cnt"]}
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/trends")
async def api_trends(days: int = 30, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT date, total_active_jobs, jobs_added, jobs_removed
               FROM daily_snapshots ORDER BY date DESC LIMIT ?""",
            (days,),
        ).fetchall()
        return {
            "days": [
                {
                    "date": r["date"],
                    "total": r["total_active_jobs"],
                    "added": r["jobs_added"],
                    "removed": r["jobs_removed"],
                }
                for r in reversed(rows)
            ]
        }
    finally:
        conn.close()


@app.get("/api/alerts")
async def api_alerts(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT * FROM alerts WHERE acknowledged = 0
               ORDER BY triggered_at DESC LIMIT 20"""
        ).fetchall()
        return {
            "alerts": [
                {
                    "id": r["id"],
                    "type": r["alert_type"],
                    "severity": r["severity"],
                    "message": r["message"],
                    "time": r["triggered_at"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        terms = [f"%{_escape_like(t.strip())}%" for t in q.split(",") if t.strip()]
        if not terms:
            return {"jobs": [], "query": q}
        clauses = " OR ".join(["j.title LIKE ? ESCAPE '\\'"] * len(terms))
        rows = conn.execute(
            f"""SELECT j.id, j.title, d.name as department,
                       j.absolute_url, j.first_seen
                FROM jobs j
                LEFT JOIN departments d ON j.department_id = d.id
                WHERE j.is_active = 1 AND ({clauses})
                ORDER BY j.first_seen DESC""",
            terms,
        ).fetchall()
        return {
            "jobs": [
                {"id": r["id"], "title": r["title"],
                 "department": r["department"] or "Unknown",
                 "url": r["absolute_url"], "first_seen": r["first_seen"]}
                for r in rows
            ],
            "query": q,
        }
    finally:
        conn.close()


@app.get("/api/recent-changes")
async def api_recent_changes(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        added = conn.execute(
            """SELECT j.title, d.name as department, j.first_seen, j.absolute_url
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               ORDER BY j.first_seen DESC LIMIT 10"""
        ).fetchall()
        removed = conn.execute(
            """SELECT j.title, d.name as department, j.removed_date
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 0 AND j.removed_date IS NOT NULL
               ORDER BY j.removed_date DESC LIMIT 10"""
        ).fetchall()
        return {
            "added": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["first_seen"], "url": r["absolute_url"]}
                for r in added
            ],
            "removed": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["removed_date"]}
                for r in removed
            ],
        }
    finally:
        conn.close()


@app.get("/api/compensation")
async def api_compensation(company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT d.name as department,
                      COUNT(*) as cnt,
                      MIN(c.salary_min) as min_sal,
                      MAX(c.salary_max) as max_sal,
                      AVG((c.salary_min + c.salary_max) / 2) as avg_mid,
                      c.currency
               FROM compensation c
               JOIN jobs j ON c.job_id = j.id
               JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               GROUP BY d.name, c.currency
               ORDER BY avg_mid DESC"""
        ).fetchall()
        return {
            "compensation": [
                {
                    "department": r["department"],
                    "roles_with_data": r["cnt"],
                    "min": r["min_sal"] // 100 if r["min_sal"] else 0,
                    "max": r["max_sal"] // 100 if r["max_sal"] else 0,
                    "avg_mid": int(r["avg_mid"]) // 100 if r["avg_mid"] else 0,
                    "currency": r["currency"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


# --- htmx partials ---


@app.get("/partials/summary", response_class=HTMLResponse)
async def partial_summary(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        snap = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return templates.TemplateResponse(request, "partials/summary.html", context={
            "snap": snap,
        })
    finally:
        conn.close()


@app.get("/partials/departments", response_class=HTMLResponse)
async def partial_departments(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT d.name, COUNT(*) as cnt
               FROM jobs j JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               GROUP BY d.name ORDER BY cnt DESC"""
        ).fetchall()
        total = sum(r["cnt"] for r in rows)
        max_count = rows[0]["cnt"] if rows else 1
        depts = [
            {"name": r["name"], "count": r["cnt"],
             "pct": round(r["cnt"] / total * 100, 1) if total else 0,
             "bar_width": round(r["cnt"] / max_count * 100)}
            for r in rows
        ]
        return templates.TemplateResponse(request, "partials/departments.html", context={
            "departments": depts,
            "total": total,
        })
    finally:
        conn.close()


@app.get("/partials/locations", response_class=HTMLResponse)
async def partial_locations(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT location_name, COUNT(*) as cnt
               FROM job_locations jl JOIN jobs j ON jl.job_id = j.id
               WHERE j.is_active = 1
               GROUP BY location_name ORDER BY cnt DESC"""
        ).fetchall()
        return templates.TemplateResponse(request, "partials/locations.html", context={
            "locations": [{"name": r["location_name"], "count": r["cnt"]} for r in rows],
        })
    finally:
        conn.close()


@app.get("/partials/trends", response_class=HTMLResponse)
async def partial_trends(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT date, total_active_jobs, jobs_added, jobs_removed
               FROM daily_snapshots ORDER BY date DESC LIMIT 30"""
        ).fetchall()
        days = list(reversed(rows))
        return templates.TemplateResponse(request, "partials/trends.html", context={
            "days": [
                {"date": r["date"], "total": r["total_active_jobs"],
                 "added": r["jobs_added"], "removed": r["jobs_removed"]}
                for r in days
            ],
        })
    finally:
        conn.close()


@app.get("/partials/alerts", response_class=HTMLResponse)
async def partial_alerts(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT * FROM alerts WHERE acknowledged = 0
               ORDER BY triggered_at DESC LIMIT 10"""
        ).fetchall()
        return templates.TemplateResponse(request, "partials/alerts.html", context={
            "alerts": [
                {"type": r["alert_type"], "severity": r["severity"],
                 "message": r["message"], "time": r["triggered_at"]}
                for r in rows
            ],
        })
    finally:
        conn.close()


@app.get("/partials/search", response_class=HTMLResponse)
async def partial_search(
    request: Request,
    q: str = Query("", min_length=0),
    company: str | None = X_COMPANY_HEADER,
):
    if not q.strip():
        return templates.TemplateResponse(request, "partials/search.html", context={
            "jobs": [], "query": "", "empty": True,
        })
    conn = _db(company)
    try:
        terms = [f"%{_escape_like(t.strip())}%" for t in q.split(",") if t.strip()]
        if not terms:
            return templates.TemplateResponse(request, "partials/search.html", context={
                "jobs": [], "query": "", "empty": True,
            })
        clauses = " OR ".join(["j.title LIKE ? ESCAPE '\\'"] * len(terms))
        rows = conn.execute(
            f"""SELECT j.id, j.title, d.name as department,
                       j.absolute_url, j.first_seen
                FROM jobs j
                LEFT JOIN departments d ON j.department_id = d.id
                WHERE j.is_active = 1 AND ({clauses})
                ORDER BY d.name, j.title""",
            terms,
        ).fetchall()
        return templates.TemplateResponse(request, "partials/search.html", context={
            "jobs": [
                {"id": r["id"], "title": r["title"],
                 "department": r["department"] or "Unknown",
                 "url": r["absolute_url"], "first_seen": r["first_seen"]}
                for r in rows
            ],
            "query": q,
            "empty": False,
        })
    finally:
        conn.close()


@app.get("/partials/recent", response_class=HTMLResponse)
async def partial_recent(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        added = conn.execute(
            """SELECT j.title, d.name as department, j.first_seen, j.absolute_url
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               ORDER BY j.first_seen DESC LIMIT 8"""
        ).fetchall()
        removed = conn.execute(
            """SELECT j.title, d.name as department, j.removed_date
               FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 0 AND j.removed_date IS NOT NULL
               ORDER BY j.removed_date DESC LIMIT 8"""
        ).fetchall()
        return templates.TemplateResponse(request, "partials/recent.html", context={
            "added": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["first_seen"], "url": r["absolute_url"]}
                for r in added
            ],
            "removed": [
                {"title": r["title"], "department": r["department"] or "Unknown",
                 "date": r["removed_date"]}
                for r in removed
            ],
        })
    finally:
        conn.close()


@app.get("/partials/compensation", response_class=HTMLResponse)
async def partial_compensation(request: Request, company: str | None = X_COMPANY_HEADER):
    conn = _db(company)
    try:
        rows = conn.execute(
            """SELECT d.name as department,
                      COUNT(*) as cnt,
                      MIN(c.salary_min) as min_sal,
                      MAX(c.salary_max) as max_sal,
                      AVG((c.salary_min + c.salary_max) / 2) as avg_mid,
                      c.currency
               FROM compensation c
               JOIN jobs j ON c.job_id = j.id
               JOIN departments d ON j.department_id = d.id
               WHERE j.is_active = 1
               GROUP BY d.name, c.currency
               ORDER BY avg_mid DESC"""
        ).fetchall()
        comp = [
            {"department": r["department"], "count": r["cnt"],
             "min": f"${r['min_sal'] // 100:,}" if r["min_sal"] else "N/A",
             "max": f"${r['max_sal'] // 100:,}" if r["max_sal"] else "N/A",
             "avg": f"${int(r['avg_mid']) // 100:,}" if r["avg_mid"] else "N/A",
             "currency": r["currency"]}
            for r in rows
        ]
        return templates.TemplateResponse(request, "partials/compensation.html", context={
            "compensation": comp,
        })
    finally:
        conn.close()


def _build_dashboard_data(conn, snap) -> dict:
    """Build all data needed for the full dashboard render."""
    if not snap:
        return {
            "snap": None, "departments": [], "locations": [],
            "days": [], "alerts": [], "compensation": [],
            "recent_added": [], "recent_removed": [], "total": 0,
        }

    # Departments
    dept_rows = conn.execute(
        """SELECT d.name, COUNT(*) as cnt
           FROM jobs j JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           GROUP BY d.name ORDER BY cnt DESC"""
    ).fetchall()
    total = sum(r["cnt"] for r in dept_rows)
    max_count = dept_rows[0]["cnt"] if dept_rows else 1
    departments = [
        {"name": r["name"], "count": r["cnt"],
         "pct": round(r["cnt"] / total * 100, 1) if total else 0,
         "bar_width": round(r["cnt"] / max_count * 100)}
        for r in dept_rows
    ]

    # Locations
    loc_rows = conn.execute(
        """SELECT location_name, COUNT(*) as cnt
           FROM job_locations jl JOIN jobs j ON jl.job_id = j.id
           WHERE j.is_active = 1
           GROUP BY location_name ORDER BY cnt DESC"""
    ).fetchall()
    locations = [{"name": r["location_name"], "count": r["cnt"]} for r in loc_rows]

    # Trends
    trend_rows = conn.execute(
        """SELECT date, total_active_jobs, jobs_added, jobs_removed
           FROM daily_snapshots ORDER BY date DESC LIMIT 30"""
    ).fetchall()
    days = [
        {"date": r["date"], "total": r["total_active_jobs"],
         "added": r["jobs_added"], "removed": r["jobs_removed"]}
        for r in reversed(trend_rows)
    ]

    # Alerts
    alert_rows = conn.execute(
        """SELECT * FROM alerts WHERE acknowledged = 0
           ORDER BY triggered_at DESC LIMIT 10"""
    ).fetchall()
    alerts = [
        {"type": r["alert_type"], "severity": r["severity"],
         "message": r["message"], "time": r["triggered_at"]}
        for r in alert_rows
    ]

    # Compensation (raw numbers for charting)
    comp_rows = conn.execute(
        """SELECT d.name as department, COUNT(*) as cnt,
                  MIN(c.salary_min) as min_sal, MAX(c.salary_max) as max_sal,
                  AVG((c.salary_min + c.salary_max) / 2) as avg_mid, c.currency
           FROM compensation c
           JOIN jobs j ON c.job_id = j.id
           JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           GROUP BY d.name, c.currency ORDER BY avg_mid DESC"""
    ).fetchall()
    compensation = [
        {"department": r["department"], "count": r["cnt"],
         "min": r["min_sal"] // 100 if r["min_sal"] else 0,
         "max": r["max_sal"] // 100 if r["max_sal"] else 0,
         "avg": int(r["avg_mid"]) // 100 if r["avg_mid"] else 0,
         "currency": r["currency"]}
        for r in comp_rows
    ]

    # Recent changes
    added_rows = conn.execute(
        """SELECT j.title, d.name as department, j.first_seen, j.absolute_url
           FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 1
           ORDER BY j.first_seen DESC LIMIT 8"""
    ).fetchall()
    removed_rows = conn.execute(
        """SELECT j.title, d.name as department, j.removed_date
           FROM jobs j LEFT JOIN departments d ON j.department_id = d.id
           WHERE j.is_active = 0 AND j.removed_date IS NOT NULL
           ORDER BY j.removed_date DESC LIMIT 8"""
    ).fetchall()

    return {
        "snap": snap,
        "departments": departments,
        "locations": locations,
        "days": days,
        "alerts": alerts,
        "compensation": compensation,
        "recent_added": [
            {"title": r["title"], "department": r["department"] or "Unknown",
             "date": r["first_seen"], "url": r["absolute_url"]}
            for r in added_rows
        ],
        "recent_removed": [
            {"title": r["title"], "department": r["department"] or "Unknown",
             "date": r["removed_date"]}
            for r in removed_rows
        ],
        "total": total,
    }
```

- [ ] **Step 4: Add company tabs and header inheritance to `base.html`**

Replace `src/anthropic_tracker/templates/base.html` in full:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Anthropic Hiring Tracker{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  {% block head %}{% endblock %}
</head>
<body hx-headers='{"X-Company": "{{ company }}"}'>
  <header>
    <div class="header-left">
      <h1>Anthropic Hiring Tracker</h1>
      <nav class="company-tabs">
        {% for c in companies %}
        <a href="/?company={{ c }}" class="company-tab{% if c == company %} active{% endif %}">{{ c }}</a>
        {% endfor %}
      </nav>
    </div>
    <div class="header-right">
      <span class="pulse"></span>
      <span class="header-label">Live</span>
    </div>
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
  <footer>
    <span class="muted">Auto-refreshes every 60s</span>
  </footer>
</body>
</html>
```

- [ ] **Step 5: Style the company tabs in `style.css`**

In `src/anthropic_tracker/static/style.css`, immediately after the existing `header h1 { ... }` rule (the block ending at line 47), insert:

```css
.header-left {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.company-tabs {
  display: flex;
  gap: 0.4rem;
}

.company-tab {
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  font-size: 0.8rem;
  color: var(--muted);
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.company-tab:hover {
  background: var(--surface-hover);
  color: var(--text);
}

.company-tab.active {
  background: var(--accent-dim);
  color: var(--accent);
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_web.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add src/anthropic_tracker/web.py src/anthropic_tracker/templates/base.html src/anthropic_tracker/static/style.css tests/test_web.py
git commit -m "feat: route the web dashboard per company via header, query param, and tabs"
```

- [ ] **Step 8: Run the full suite to confirm nothing else regressed**

Run: `pytest -v`
Expected: PASS (all tests)

---

### Task 3: Docker Compose and README documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `TRACKER_COMPANIES` env var as defined in Task 1's `config.get_companies()`. No code interfaces produced.

- [ ] **Step 1: Add `TRACKER_COMPANIES` to the shared Docker Compose environment block**

In `docker-compose.yml`, the shared `x-image` anchor currently has:

```yaml
  environment:
    TRACKER_DB: /data/tracker.db
```

Change it to:

```yaml
  environment:
    TRACKER_DB: /data/tracker.db
    TRACKER_COMPANIES: anthropic
```

Since `web`, `tracker`, and `tracker-fetch` all merge in this anchor via `<<: *image`, this one line covers all three services.

- [ ] **Step 2: Verify the Compose config is valid and the env var propagates**

Run: `docker compose config`
Expected: the rendered YAML shows `TRACKER_COMPANIES: anthropic` under `environment:` for all three services (`web`, `tracker`, `tracker-fetch`).

- [ ] **Step 3: Document `TRACKER_COMPANIES` in the README**

In `README.md`, replace the Configuration table (currently a single `TRACKER_DB` row):

```markdown
## Configuration

Environment:

| Var | Default | Purpose |
|---|---|---|
| `TRACKER_DB` | `~/.anthropic-tracker/tracker.db` (local) / `/data/tracker.db` (Docker) | SQLite path (see `TRACKER_COMPANIES` below for how this is suffixed) |
| `TRACKER_COMPANIES` | `anthropic` | Comma-separated Greenhouse board slugs to track, e.g. `anthropic,openai,notion` |

Config constants in `src/anthropic_tracker/config.py`: timeouts, retry policy, alert thresholds.

**Tracking more than one company:** set `TRACKER_COMPANIES` to a comma-separated
list of Greenhouse board slugs. Each company gets its own database file
(`tracker-{slug}.db` next to wherever `TRACKER_DB` points), its own history, and
its own alerts. `tracker fetch` with no `--company` flag fetches every configured
company in one run; the web dashboard grows a tab per company.

**Migrating an existing single-company install:** switching from one company to
several does *not* automatically rename your existing `tracker.db`. Rename it
yourself to match the new per-company naming, e.g.:

```bash
mv ~/.anthropic-tracker/tracker.db ~/.anthropic-tracker/tracker-anthropic.db
# or, in the Docker volume:
docker compose run --rm tracker sh -c "mv /data/tracker.db /data/tracker-anthropic.db"
```

This is a manual step by design — an automatic rename risks silently clobbering
data if anything goes wrong.
```

Also update the "Local (development)" section's fetch line to mention `--company`. Replace:

```markdown
tracker fetch --with-salary    # populates ~/.anthropic-tracker/tracker.db
```

with:

```markdown
tracker fetch --with-salary    # populates ~/.anthropic-tracker/tracker.db (or one file per TRACKER_COMPANIES)
tracker --company openai fetch # scope any command to a single company
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml README.md
git commit -m "docs: document TRACKER_COMPANIES and the manual single-to-multi migration step"
```
