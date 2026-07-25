"""Provider-independent ingestion planning and orchestration."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ferminator.adapters import ADAPTERS
from ferminator.domain import BoardRef, NormalizedJob


class UnsafeRemovalError(RuntimeError):
    """Raised when a provider response would remove an implausible job share."""


class InvalidBoardResponseError(RuntimeError):
    """Raised when a nominally successful board response is structurally unsafe."""


@dataclass(frozen=True)
class LifecyclePlan:
    added: frozenset[str]
    present: frozenset[str]
    removed: frozenset[str]
    reactivated: frozenset[str]


@dataclass(frozen=True)
class IngestionPolicy:
    max_removal_fraction: float = 0.35
    allow_empty_board: bool = False


@dataclass(frozen=True)
class IngestionResult:
    board: BoardRef
    fetched: int
    added: int
    updated: int
    removed: int
    reactivated: int
    run_id: str


@dataclass(frozen=True)
class BoardFetch:
    board: BoardRef
    jobs: tuple[NormalizedJob, ...]
    duration_ms: int


@dataclass(frozen=True)
class BoardFailure:
    board: BoardRef
    error_code: str


@dataclass(frozen=True)
class BulkIngestionResult:
    succeeded: tuple[IngestionResult, ...]
    failed: tuple[BoardFailure, ...]
    fetch_duration_ms: int


class IngestionRepository(Protocol):
    def active_source_ids(self, board: BoardRef) -> set[str]: ...
    def known_source_ids(self, board: BoardRef) -> set[str]: ...
    def apply_ingestion(
        self,
        board: BoardRef,
        jobs: list[NormalizedJob],
        plan: LifecyclePlan,
        idempotency_key: str,
    ) -> IngestionResult: ...
    def record_ingestion_failure(
        self,
        board: BoardRef,
        *,
        idempotency_key: str,
        error_code: str,
    ) -> None: ...


def ingestion_idempotency_key(board: BoardRef, at: datetime | None = None) -> str:
    """Return a stable per-board key so retries cannot create duplicate runs."""
    timestamp_bucket = (at or datetime.now(UTC)).strftime("%Y%m%d%H")
    identity = f"{board.provider}:{board.board_key}:{board.region}:{timestamp_bucket}"
    return hashlib.sha256(identity.encode()).hexdigest()


def plan_lifecycle(
    *,
    active_ids: set[str],
    known_ids: set[str],
    incoming_ids: set[str],
    policy: IngestionPolicy | None = None,
) -> LifecyclePlan:
    """Plan additions, removals, and reactivations with mass-removal protection."""
    policy = policy or IngestionPolicy()
    if active_ids and not incoming_ids and not policy.allow_empty_board:
        raise UnsafeRemovalError("Empty response would remove every active job")
    removed = active_ids - incoming_ids
    if active_ids:
        removal_fraction = len(removed) / len(active_ids)
        if removal_fraction > policy.max_removal_fraction:
            raise UnsafeRemovalError(
                f"Removal fraction {removal_fraction:.1%} exceeds "
                f"{policy.max_removal_fraction:.1%} safety limit"
            )
    return LifecyclePlan(
        added=frozenset(incoming_ids - known_ids),
        present=frozenset(incoming_ids),
        removed=frozenset(removed),
        reactivated=frozenset((known_ids - active_ids) & incoming_ids),
    )


def run_board_ingestion(
    board: BoardRef,
    repository: IngestionRepository,
    *,
    policy: IngestionPolicy | None = None,
) -> IngestionResult:
    """Fetch, normalize, safety-check, and atomically apply one ATS board."""
    idempotency_key = ingestion_idempotency_key(board)
    try:
        with ADAPTERS[board.provider]() as adapter:
            jobs = adapter.fetch_jobs(board)
    except Exception as exc:
        repository.record_ingestion_failure(
            board,
            idempotency_key=idempotency_key,
            error_code=getattr(exc, "code", type(exc).__name__),
        )
        raise
    source_ids = [job.source_job_id for job in jobs]
    if len(source_ids) != len(set(source_ids)):
        error = InvalidBoardResponseError("Provider returned duplicate job identifiers")
        repository.record_ingestion_failure(
            board,
            idempotency_key=idempotency_key,
            error_code="duplicate_source_job_id",
        )
        raise error
    incoming_ids = {job.source_job_id for job in jobs}
    plan = plan_lifecycle(
        active_ids=repository.active_source_ids(board),
        known_ids=repository.known_source_ids(board),
        incoming_ids=incoming_ids,
        policy=policy,
    )
    return repository.apply_ingestion(board, jobs, plan, idempotency_key)


def fetch_board(board: BoardRef) -> BoardFetch:
    """Fetch and validate a board without holding a database connection."""
    started = time.monotonic()
    with ADAPTERS[board.provider]() as adapter:
        jobs = adapter.fetch_jobs(board)
    source_ids = [job.source_job_id for job in jobs]
    if len(source_ids) != len(set(source_ids)):
        raise InvalidBoardResponseError("Provider returned duplicate job identifiers")
    return BoardFetch(
        board=board,
        jobs=tuple(jobs),
        duration_ms=round((time.monotonic() - started) * 1000),
    )


def apply_board_fetch(
    fetched: BoardFetch,
    repository: IngestionRepository,
    *,
    policy: IngestionPolicy | None = None,
) -> IngestionResult:
    """Apply a previously fetched board through the normal lifecycle safeguards."""
    board = fetched.board
    incoming_ids = {job.source_job_id for job in fetched.jobs}
    plan = plan_lifecycle(
        active_ids=repository.active_source_ids(board),
        known_ids=repository.known_source_ids(board),
        incoming_ids=incoming_ids,
        policy=policy,
    )
    return repository.apply_ingestion(
        board,
        list(fetched.jobs),
        plan,
        ingestion_idempotency_key(board),
    )


def run_bulk_ingestion(
    boards: list[BoardRef],
    repository: IngestionRepository,
    *,
    max_workers: int = 8,
    policy: IngestionPolicy | None = None,
    progress: Callable[[BoardRef, IngestionResult | None, str | None], None] | None = None,
) -> BulkIngestionResult:
    """Fetch boards concurrently, then apply each result with bounded DB pressure."""
    if max_workers < 1 or max_workers > 16:
        raise ValueError("max_workers must be between 1 and 16")
    fetch_started = time.monotonic()
    fetched: list[BoardFetch] = []
    failures: list[BoardFailure] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(boards))) as executor:
        futures = {executor.submit(fetch_board, board): board for board in boards}
        for future in as_completed(futures):
            board = futures[future]
            try:
                fetched.append(future.result())
            except Exception as exc:
                error_code = str(getattr(exc, "code", type(exc).__name__))[:120]
                repository.record_ingestion_failure(
                    board,
                    idempotency_key=ingestion_idempotency_key(board),
                    error_code=error_code,
                )
                failures.append(BoardFailure(board=board, error_code=error_code))
                if progress:
                    progress(board, None, error_code)
    fetch_duration_ms = round((time.monotonic() - fetch_started) * 1000)
    succeeded: list[IngestionResult] = []
    for item in sorted(fetched, key=lambda value: value.board.company_slug):
        try:
            result = apply_board_fetch(item, repository, policy=policy)
            succeeded.append(result)
            if progress:
                progress(item.board, result, None)
        except Exception as exc:
            error_code = str(getattr(exc, "code", type(exc).__name__))[:120]
            repository.record_ingestion_failure(
                item.board,
                idempotency_key=ingestion_idempotency_key(item.board),
                error_code=error_code,
            )
            failures.append(BoardFailure(board=item.board, error_code=error_code))
            if progress:
                progress(item.board, None, error_code)
    return BulkIngestionResult(
        succeeded=tuple(succeeded),
        failed=tuple(failures),
        fetch_duration_ms=fetch_duration_ms,
    )
