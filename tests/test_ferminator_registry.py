from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ferminator.cli import _boards_for_shard
from ferminator.domain import ATSProvider, BoardRef
from ferminator.registry import CompanyRegistry


def test_private_registry_is_not_committed_to_source() -> None:
    assert not Path("config/companies.yaml").exists()
    assert not list(Path("docs").glob("board-validation-*.json"))


def test_registry_rejects_duplicate_board_identity() -> None:
    payload = {
        "schema_version": 1,
        "companies": [
            {
                "slug": "one",
                "name": "One",
                "boards": [
                    {
                        "provider": "greenhouse",
                        "board_key": "same",
                        "source_url": "https://example.com/one",
                    }
                ],
            },
            {
                "slug": "two",
                "name": "Two",
                "boards": [
                    {
                        "provider": "greenhouse",
                        "board_key": "same",
                        "source_url": "https://example.com/two",
                    }
                ],
            },
        ],
    }

    with pytest.raises(ValidationError, match="combinations must be unique"):
        CompanyRegistry.model_validate(payload)


def test_scheduled_scan_pulls_twice_daily_and_scores_once() -> None:
    workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")

    assert "timeout-minutes: 60" in workflow
    assert "timezone: America/Los_Angeles" in workflow
    # Off the hour on purpose: the top of the hour is GitHub's documented
    # high-load window, and both slots were routinely delayed or dropped there.
    assert 'cron: "11 6 * * *"' in workflow
    assert 'cron: "41 15 * * *"' in workflow
    assert '"0 6 * * *"' not in workflow and '"0 15 * * *"' not in workflow
    # Shards must not score. Scoring inside every shard would re-score the whole
    # corpus once per shard, each against a half-updated set of jobs.
    assert "--ingest-only" in workflow
    assert "ferminator rescore" in workflow
    assert "needs: pull" in workflow


def test_digest_env_is_declared_at_job_level() -> None:
    """A step's own `env:` block is not visible to that step's `if:`.

    The digest step guards on `env.SMTP_HOST != ''` while declaring SMTP_HOST in
    its own env block, so the guard always saw an empty string and the send was
    skipped on every single run. The env has to live on the job.
    """
    workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")
    score = workflow.split("  score:", 1)[1]
    job_env, steps = score.split("    steps:", 1)

    assert "SMTP_HOST:" in job_env, "SMTP_HOST must be job-level for the if: guard to see it"
    send = steps.split("- name: Send ranked digests", 1)[1].split("- name:", 1)[0]
    assert "env:" not in send, "re-declaring env on the send step reintroduces the skip bug"


def test_every_ats_provider_is_covered_by_the_scan_matrix() -> None:
    """A provider missing from the matrix is never pulled, silently.

    Adding a provider to ATSProvider without assigning it to a shard would drop
    every board on it out of the schedule with no error anywhere.

    A provider may appear in more than one entry only when those entries
    sub-shard it, as Workday does. In that case the declared indices have to
    cover 1..count exactly, or some of its boards are never fetched.
    """
    workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")

    entries: list[dict[str, str]] = []
    for line in workflow.splitlines():
        stripped = line.strip()
        for field in ("name", "providers", "index", "count"):
            prefix = f"- {field}:" if field == "name" else f"{field}:"
            if stripped.startswith(prefix):
                value = stripped.split(":", 1)[1].strip()
                if field == "name":
                    entries.append({})
                if entries and value and "Providers to pull" not in value:
                    entries[-1][field] = value

    shards = [e for e in entries if "providers" in e]
    assert shards, "no matrix entries parsed out of the workflow"

    covered: dict[str, list[tuple[int, int]]] = {}
    for entry in shards:
        for provider in (p.strip() for p in entry["providers"].split(",")):
            if provider:
                covered.setdefault(provider, []).append(
                    (int(entry["index"]), int(entry["count"]))
                )

    supported = {provider.value for provider in ATSProvider}
    missing = supported - covered.keys()
    assert not missing, f"providers never pulled by any shard: {sorted(missing)}"

    for provider, slots in covered.items():
        counts = {count for _, count in slots}
        assert len(counts) == 1, f"{provider} declares conflicting shard counts: {counts}"
        count = counts.pop()
        assert sorted(index for index, _ in slots) == list(range(1, count + 1)), (
            f"{provider} is split into {count} shards but its declared indices "
            f"are {sorted(index for index, _ in slots)}; some boards would never be fetched"
        )


def test_registry_shards_are_stable_complete_and_non_overlapping() -> None:
    boards = [
        BoardRef(
            provider=ATSProvider.GREENHOUSE,
            company_slug=f"sample-{index}",
            company_name=f"Sample {index}",
            board_key=f"sample-{index}",
            source_url=f"https://example.com/jobs/{index}",
        )
        for index in range(40)
    ]
    first = _boards_for_shard(boards, shard_index=1, shard_count=2)
    second = _boards_for_shard(boards, shard_index=2, shard_count=2)
    def identity(board):
        return board.provider, board.board_key, board.region

    assert {identity(board) for board in first}.isdisjoint(
        {identity(board) for board in second}
    )
    assert {identity(board) for board in first + second} == {
        identity(board) for board in boards
    }
    assert first == _boards_for_shard(boards, shard_index=1, shard_count=2)
    assert abs(len(first) - len(second)) <= len(boards) * 0.1
