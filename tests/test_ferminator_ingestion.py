from __future__ import annotations

import pytest

from ferminator.domain import ATSProvider, BoardRef
from ferminator.ingestion import (
    BoardFetch,
    IngestionPolicy,
    IngestionResult,
    InvalidBoardResponseError,
    UnsafeRemovalError,
    plan_lifecycle,
    run_board_ingestion,
    run_bulk_ingestion,
)


def test_lifecycle_classifies_add_remove_and_reactivate() -> None:
    plan = plan_lifecycle(
        active_ids={"active", "remove"},
        known_ids={"active", "remove", "returning"},
        incoming_ids={"active", "returning", "new"},
        policy=IngestionPolicy(max_removal_fraction=0.5),
    )

    assert plan.added == {"new"}
    assert plan.removed == {"remove"}
    assert plan.reactivated == {"returning"}
    assert plan.present == {"active", "returning", "new"}


def test_lifecycle_rejects_empty_response_for_active_board() -> None:
    with pytest.raises(UnsafeRemovalError, match="Empty response"):
        plan_lifecycle(
            active_ids={"one"},
            known_ids={"one"},
            incoming_ids=set(),
        )


def test_lifecycle_rejects_suspicious_mass_removal() -> None:
    with pytest.raises(UnsafeRemovalError, match="Removal fraction"):
        plan_lifecycle(
            active_ids={"one", "two", "three"},
            known_ids={"one", "two", "three"},
            incoming_ids={"one"},
        )


def test_duplicate_provider_ids_are_recorded_as_failure(monkeypatch) -> None:
    board = BoardRef(
        provider=ATSProvider.GREENHOUSE,
        board_key="example",
        company_slug="example-company",
        company_name="Example Company",
        source_url="https://example.com/jobs",
    )
    job = type("Job", (), {"source_job_id": "duplicate"})()

    class Adapter:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_jobs(self, _board):
            return [job, job]

    class Repository:
        def __init__(self):
            self.failure = None

        def record_ingestion_failure(self, _board, **kwargs):
            self.failure = kwargs

    repository = Repository()
    monkeypatch.setitem(
        __import__("ferminator.ingestion", fromlist=["ADAPTERS"]).ADAPTERS,
        ATSProvider.GREENHOUSE,
        Adapter,
    )

    with pytest.raises(InvalidBoardResponseError):
        run_board_ingestion(board, repository)

    assert repository.failure["error_code"] == "duplicate_source_job_id"


def test_bulk_ingestion_isolates_fetch_failure(monkeypatch) -> None:
    first = BoardRef(
        provider=ATSProvider.GREENHOUSE,
        board_key="first",
        company_slug="first",
        company_name="First",
        source_url="https://job-boards.greenhouse.io/first",
    )
    second = first.model_copy(
        update={"board_key": "second", "company_slug": "second", "company_name": "Second"}
    )
    job = type("Job", (), {"source_job_id": "one"})()

    class Repository:
        def __init__(self):
            self.failures = []

        def record_ingestion_failure(self, target, **kwargs):
            self.failures.append((target, kwargs))

        def active_source_ids(self, _target):
            return set()

        def known_source_ids(self, _target):
            return set()

        def apply_ingestion(self, target, jobs, _plan, idempotency_key):
            return IngestionResult(
                board=target,
                fetched=len(jobs),
                added=len(jobs),
                updated=0,
                removed=0,
                reactivated=0,
                run_id=idempotency_key,
            )

    def fake_fetch(target):
        if target.board_key == "second":
            raise RuntimeError("provider down")
        return BoardFetch(board=target, jobs=(job,), duration_ms=5)

    repository = Repository()
    monkeypatch.setattr("ferminator.ingestion.fetch_board", fake_fetch)
    result = run_bulk_ingestion([first, second], repository, max_workers=2)

    assert [item.board.board_key for item in result.succeeded] == ["first"]
    assert [item.board.board_key for item in result.failed] == ["second"]
    assert repository.failures[0][1]["error_code"] == "RuntimeError"
