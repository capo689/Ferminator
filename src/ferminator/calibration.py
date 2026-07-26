"""Frozen calibration corpus loading and integrity checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CALIBRATION_VERSION = "ferminator_calibration_v1"
EXPECTED_CORPUS_SHA256 = "5189412b9bd4f214a49c1edbedb4618917599d4141c1d66e9fb498c64ba2f36a"


@dataclass(frozen=True)
class CalibrationSummary:
    records: int
    known_adam_verdicts: int
    final_reviewer_scores: int
    live_verified: int
    recommendation_counts: dict[str, int]


def load_calibration(path: str | Path) -> list[dict[str, Any]]:
    """Load V1 without silently accepting mutation or malformed records."""
    source = Path(path)
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED_CORPUS_SHA256:
        raise ValueError("Calibration V1 integrity check failed")
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record_ids: set[str] = set()
    for record in records:
        if record.get("schema_version") != CALIBRATION_VERSION:
            raise ValueError("Unexpected calibration schema version")
        required = ("record_id", "company", "exact_job_title", "job_url", "full_job_description")
        if any(not record.get(field) for field in required):
            raise ValueError(f"Incomplete calibration record: {record.get('record_id')}")
        if record["record_id"] in record_ids:
            raise ValueError(f"Duplicate calibration record: {record['record_id']}")
        record_ids.add(record["record_id"])
    return records


def summarize_calibration(records: list[dict[str, Any]]) -> CalibrationSummary:
    counts: dict[str, int] = {}
    for record in records:
        recommendation = record["reviewer"]["recommendation"]
        counts[recommendation] = counts.get(recommendation, 0) + 1
    return CalibrationSummary(
        records=len(records),
        known_adam_verdicts=sum(r["adam"]["verdict"] != "unknown" for r in records),
        final_reviewer_scores=sum(
            r["reviewer"]["final_reviewer_score"] is not None for r in records
        ),
        live_verified=sum(r["source"]["live_verified"] is True for r in records),
        recommendation_counts=counts,
    )
