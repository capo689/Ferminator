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


def test_scheduled_scan_capacity_matches_expanded_registry() -> None:
    workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")

    assert "timeout-minutes: 45" in workflow
    assert "timezone: America/Los_Angeles" in workflow
    assert 'cron: "5 8,16 * * *"' in workflow
    assert 'cron: "35 8,16 * * *"' in workflow
    assert '--shard-index "$REQUESTED_SHARD" --shard-count 2' in workflow


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
