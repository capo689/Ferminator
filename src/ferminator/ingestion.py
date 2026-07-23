"""Provider-independent ingestion planning and orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ferminator.adapters import ADAPTERS
from ferminator.domain import BoardRef, NormalizedJob


class UnsafeRemovalError(RuntimeError):
    """Raised when a provider response would remove an implausible job share."""


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
    with ADAPTERS[board.provider]() as adapter:
        jobs = adapter.fetch_jobs(board)
    incoming_ids = {job.source_job_id for job in jobs}
    plan = plan_lifecycle(
        active_ids=repository.active_source_ids(board),
        known_ids=repository.known_source_ids(board),
        incoming_ids=incoming_ids,
        policy=policy,
    )
    timestamp_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
    identity = f"{board.provider}:{board.board_key}:{timestamp_bucket}"
    idempotency_key = hashlib.sha256(identity.encode()).hexdigest()
    return repository.apply_ingestion(board, jobs, plan, idempotency_key)

