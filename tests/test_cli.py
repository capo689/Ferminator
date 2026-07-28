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


class TestCLI:
    def test_init_command(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db_path, "init"])
        assert result.exit_code == 0
        assert "initialized" in result.output.lower()

    @respx.mock
    def test_fetch_command(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _mock_api()

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db_path, "fetch"])
        assert result.exit_code == 0
        assert "5" in result.output

    @respx.mock
    def test_summary_after_fetch(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _mock_api()

        runner = CliRunner()
        runner.invoke(cli, ["--db", db_path, "fetch"])
        result = runner.invoke(cli, ["--db", db_path, "summary"])
        assert result.exit_code == 0

    @respx.mock
    def test_report_json(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _mock_api()

        runner = CliRunner()
        runner.invoke(cli, ["--db", db_path, "fetch"])
        result = runner.invoke(cli, ["--db", db_path, "report", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_active"] == 5

    @respx.mock
    def test_report_csv(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        _mock_api()

        runner = CliRunner()
        runner.invoke(cli, ["--db", db_path, "fetch"])
        result = runner.invoke(cli, ["--db", db_path, "report", "--format", "csv"])
        assert result.exit_code == 0
        assert "id,title,department" in result.output

    def test_alerts_no_data(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, ["--db", db_path, "init"])
        result = runner.invoke(cli, ["--db", db_path, "alerts"])
        assert result.exit_code == 0

    def test_trends_no_data(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        runner.invoke(cli, ["--db", db_path, "init"])
        result = runner.invoke(cli, ["--db", db_path, "trends"])
        assert result.exit_code == 0


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
    def test_group_level_company_flag_scopes_fetch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))
        _mock_api("openai")

        runner = CliRunner()
        result = runner.invoke(cli, ["--company", "openai", "fetch"])
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


class TestCompanySlugValidation:
    def test_path_traversal_company_flag_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker.db"))

        runner = CliRunner()
        result = runner.invoke(cli, ["--company", "../evil", "fetch"])
        assert result.exit_code != 0
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "Traceback" not in result.output

    def test_explicit_db_with_multiple_companies_and_no_scope_refuses(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACKER_COMPANIES", "anthropic,openai")
        db_path = str(tmp_path / "shared.db")

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", db_path, "fetch"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output


def test_digest_covers_every_active_profile_not_just_one_on_disk(monkeypatch):
    """Regression: `ferminator digest` defaulted to profiles/adam-cagle.md and
    loaded it from disk, so an account provisioned through /admin -- which
    exists only as a database row -- never received a digest at all."""
    from click.testing import CliRunner

    from ferminator import cli as cli_module
    from ferminator.profiles import load_profile

    profile = load_profile("profiles/adam-cagle.md")
    seen = []

    class Repository:
        def scannable_profiles(self):
            return [("id-a", profile), ("id-b", profile)]

        def top_matches(self, profile_id, **_kwargs):
            seen.append(profile_id)
            return []

        def close(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(cli_module, "PostgresRepository", lambda *_a, **_k: Repository())

    result = CliRunner().invoke(cli_module.cli, ["digest"])

    assert result.exit_code == 0, result.output
    assert seen == ["id-a", "id-b"], f"expected every profile, got {seen}"
    assert "2 profile(s)" in result.output


def test_digest_skips_a_profile_with_no_recipient_instead_of_failing(monkeypatch):
    """One unconfigured email_env must not stop other users' digests."""
    from click.testing import CliRunner

    from ferminator import cli as cli_module
    from ferminator.profiles import load_profile

    profile = load_profile("profiles/adam-cagle.md")

    class Repository:
        def scannable_profiles(self):
            return [("id-a", profile)]

        def top_matches(self, *_a, **_k):
            return []

        def close(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("SMTP_FROM", "from@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv(profile.profile.email_env, raising=False)
    monkeypatch.setattr(cli_module, "PostgresRepository", lambda *_a, **_k: Repository())

    result = CliRunner().invoke(cli_module.cli, ["digest", "--send"])

    assert result.exit_code == 0, result.output
    assert "skipping" in result.output
    assert "0 of 1 digest(s) sent" in result.output


def test_rescore_covers_every_active_profile_and_fetches_the_corpus_once(monkeypatch):
    """Regression: `ferminator rescore` defaulted to profiles/adam-cagle.md and
    read it from disk, so an /admin-provisioned account could not be rescored
    at all -- the third command with this same assumption.

    It must also fetch the shared corpus once, not once per person: one pool of
    jobs, many people drawing from it.
    """
    from click.testing import CliRunner

    from ferminator import cli as cli_module
    from ferminator.profiles import load_profile

    profile = load_profile("profiles/adam-cagle.md")
    calls = {"active_jobs": 0, "stored": []}

    class Repository:
        def scannable_profiles(self):
            return [("id-a", profile), ("id-b", profile)]

        def active_jobs(self):
            calls["active_jobs"] += 1
            return []

        def profile_version(self, _profile_id):
            return 1

        def store_matches(self, *, profile_id, profile_version, matches):
            calls["stored"].append(profile_id)

        def close(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(cli_module, "PostgresRepository", lambda *_a, **_k: Repository())

    result = CliRunner().invoke(cli_module.cli, ["rescore"])

    assert result.exit_code == 0, result.output
    assert calls["stored"] == ["id-a", "id-b"], "every active profile must be scored"
    assert calls["active_jobs"] == 1, (
        f"the corpus must be fetched once, not per profile (got {calls['active_jobs']})"
    )


def test_rescore_can_target_a_single_slug(monkeypatch):
    """Onboarding one person should not rescore everyone."""
    from click.testing import CliRunner

    from ferminator import cli as cli_module
    from ferminator.profiles import load_profile

    profile = load_profile("profiles/adam-cagle.md")
    stored = []

    class Repository:
        def scannable_profiles(self):
            return [("id-a", profile)]

        def active_jobs(self):
            return []

        def profile_version(self, _p):
            return 1

        def store_matches(self, *, profile_id, profile_version, matches):
            stored.append(profile_id)

        def close(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(cli_module, "PostgresRepository", lambda *_a, **_k: Repository())

    hit = CliRunner().invoke(cli_module.cli, ["rescore", "--slug", profile.profile.slug])
    assert hit.exit_code == 0, hit.output
    assert stored == ["id-a"]

    miss = CliRunner().invoke(cli_module.cli, ["rescore", "--slug", "nobody-here"])
    assert miss.exit_code != 0
    assert "No active profile matches slug" in miss.output


def _scan_repository_stub(board_count: int):
    """Minimal repository double for `ferminator scan --ingest-only`."""
    from ferminator.domain import ATSProvider, BoardRef

    boards = [
        BoardRef(
            provider=ATSProvider.GREENHOUSE,
            company_slug=f"c{index}",
            company_name=f"C{index}",
            board_key=f"c{index}",
            source_url=f"https://example.com/{index}",
        )
        for index in range(board_count)
    ]

    class Repository:
        def enabled_boards(self):
            return boards

        def scan_lock(self, key="full-scan"):
            from contextlib import nullcontext

            return nullcontext()

        def fail_interrupted_scans(self, *_a, **_k):
            return 0

        def start_scan(self, *_a, **_k):
            return "scan-id"

        def finish_scan(self, *_a, **_k):
            return None

        def sync_profile(self, *_a, **_k):
            return "profile-id"

        def close(self):
            pass

    return Repository(), boards


def _run_scan(monkeypatch, *, board_count, failures, extra_args=()):
    from click.testing import CliRunner

    from ferminator import cli as cli_module

    repository, boards = _scan_repository_stub(board_count)

    class Bulk:
        succeeded = boards[failures:]
        failed = [
            type("Item", (), {"board": board, "error_code": "UnsafeRemovalError"})()
            for board in boards[:failures]
        ]
        fetch_duration_ms = 10.0

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(cli_module, "PostgresRepository", lambda *_a, **_k: repository)
    monkeypatch.setattr(cli_module, "run_bulk_ingestion", lambda *_a, **_k: Bulk())

    return CliRunner().invoke(cli_module.cli, ["scan", "--ingest-only", *extra_args])


def test_one_flaky_board_does_not_fail_the_whole_shard(monkeypatch):
    """Regression: any single board failure used to fail the entire run.

    A board pausing, a provider blip, or the mass-removal guard refusing a
    shrunken response are all routine across 640 boards pulled twice a day.
    Failing on one leaves every scheduled pull permanently red, which is how a
    real outage stops being noticed.
    """
    result = _run_scan(monkeypatch, board_count=262, failures=1)

    assert result.exit_code == 0, result.output
    assert "1 of 262 boards failed" in result.output


def test_a_provider_that_is_actually_down_still_fails_the_run(monkeypatch):
    """The tolerance must not swallow a real outage."""
    result = _run_scan(monkeypatch, board_count=262, failures=200)

    assert result.exit_code == 1
    assert "beyond the tolerated" in result.output


def test_a_small_provider_is_not_failed_by_its_first_flaky_board(monkeypatch):
    """Regression: providers are scanned one at a time, and some are tiny.

    Workable holds ten boards, so a bare 5% rate would fail the shard on a
    single flaky board there while tolerating thirteen on Greenhouse. The
    absolute floor is what makes the tolerance mean the same thing to a small
    provider as to a large one.
    """
    result = _run_scan(monkeypatch, board_count=10, failures=1)

    assert result.exit_code == 0, result.output
    assert "1 of 10 boards failed" in result.output


def test_a_small_provider_still_fails_when_most_of_it_is_down(monkeypatch):
    result = _run_scan(monkeypatch, board_count=10, failures=6)

    assert result.exit_code == 1


def test_failure_tolerance_is_configurable(monkeypatch):
    """--max-failure-rate only raises the allowance; the floor is the minimum."""
    result = _run_scan(
        monkeypatch, board_count=262, failures=13, extra_args=("--max-failure-rate", "0")
    )

    assert result.exit_code == 1
