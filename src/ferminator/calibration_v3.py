"""Reviewed 85-job calibration corpus and deterministic quality evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ferminator.calibration_v2 import calibration_job
from ferminator.matching import matched_role_family, score_job
from ferminator.profiles import CareerProfile

CALIBRATION_VERSION = "ferminator_calibration_v3"
EXPECTED_CORPUS_SHA256 = "dcca6aba2dad69c328125cb752201b31fe7d22cccd184c0abb1afb6dbe63421d"


@dataclass(frozen=True)
class CalibrationV3Report:
    total: int
    great: int
    maybe: int
    wrong: int
    duplicate: int
    positives_visible: int
    wrong_filtered: int
    positive_recall: float
    wrong_rejection_rate: float
    disagreements: tuple[dict, ...]


def load_calibration_v3(path: str | Path) -> list[dict]:
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_CORPUS_SHA256:
        raise ValueError("Calibration V3 integrity check failed")
    records = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    if len(records) != 85:
        raise ValueError("Calibration V3 must contain exactly 85 records")
    ids = set()
    for record in records:
        if record.get("schema_version") != CALIBRATION_VERSION:
            raise ValueError("Unexpected Calibration V3 schema version")
        if record["record_id"] in ids:
            raise ValueError("Duplicate Calibration V3 record")
        ids.add(record["record_id"])
    return records


def evaluate_calibration_v3(
    profile: CareerProfile,
    path: str | Path,
) -> CalibrationV3Report:
    records = load_calibration_v3(path)
    counts = {"great": 0, "maybe": 0, "wrong": 0, "duplicate": 0}
    positives_visible = 0
    wrong_filtered = 0
    disagreements = []
    for record in records:
        classification = record["human"]["classification"]
        counts[classification] += 1
        result = score_job(profile, calibration_job(record))
        family = matched_role_family(
            profile,
            record["exact_job_title"],
            record["full_job_description"],
        )
        visible = bool(family and result.eligible and result.score >= family.threshold)
        if classification in {"great", "maybe"} and visible:
            positives_visible += 1
        if classification == "wrong" and not visible:
            wrong_filtered += 1
        if (
            classification in {"great", "maybe"}
            and not visible
            or classification == "wrong"
            and visible
        ):
            disagreements.append(
                {
                    "job_number": record["job_number"],
                    "classification": classification,
                    "company": record["company"],
                    "title": record["exact_job_title"],
                    "score": result.score,
                    "visible": visible,
                    "concerns": result.concerns,
                }
            )
    positive_total = counts["great"] + counts["maybe"]
    return CalibrationV3Report(
        total=len(records),
        **counts,
        positives_visible=positives_visible,
        wrong_filtered=wrong_filtered,
        positive_recall=round(100 * positives_visible / positive_total, 2),
        wrong_rejection_rate=round(100 * wrong_filtered / counts["wrong"], 2),
        disagreements=tuple(disagreements),
    )
