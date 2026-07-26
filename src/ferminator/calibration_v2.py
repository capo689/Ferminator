"""Reviewed 61-job calibration corpus and deterministic quality evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ferminator.domain import (
    ATSProvider,
    JobLocation,
    NormalizedJob,
    WorkplaceType,
    extract_compensation_from_text,
)
from ferminator.matching import matched_role_family, score_job
from ferminator.profiles import CareerProfile

CALIBRATION_VERSION = "ferminator_calibration_v2"
EXPECTED_CORPUS_SHA256 = "a8b1fa58cdc3b1a10997d1608eae189f6a91bc79d91eea31009d64d41508c37a"


@dataclass(frozen=True)
class CalibrationV2Report:
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


def load_calibration_v2(path: str | Path) -> list[dict]:
    source = Path(path)
    payload = source.read_bytes()
    if hashlib.sha256(payload).hexdigest() != EXPECTED_CORPUS_SHA256:
        raise ValueError("Calibration V2 integrity check failed")
    records = [json.loads(line) for line in payload.decode().splitlines() if line.strip()]
    if len(records) != 61:
        raise ValueError("Calibration V2 must contain exactly 61 records")
    ids: set[str] = set()
    for record in records:
        if record.get("schema_version") != CALIBRATION_VERSION:
            raise ValueError("Unexpected Calibration V2 schema version")
        if record["record_id"] in ids:
            raise ValueError("Duplicate Calibration V2 record")
        ids.add(record["record_id"])
    return records


def _provider(url: str) -> ATSProvider:
    markers = (
        ("ashbyhq", ATSProvider.ASHBY),
        ("lever.co", ATSProvider.LEVER),
        ("workable", ATSProvider.WORKABLE),
        ("myworkdayjobs", ATSProvider.WORKDAY),
        ("breezy", ATSProvider.BREEZY),
        ("rippling", ATSProvider.RIPPLING),
    )
    return next((provider for marker, provider in markers if marker in url), ATSProvider.GREENHOUSE)


def calibration_job(record: dict) -> NormalizedJob:
    description = record["full_job_description"]
    company_slug = re.sub(r"[^a-z0-9]+", "-", record["company"].casefold()).strip("-")
    return NormalizedJob(
        provider=_provider(record["job_url"]),
        board_key="calibration-v2",
        source_job_id=record["record_id"],
        company_slug=company_slug,
        company_name=record["company"],
        title=record["exact_job_title"],
        description_text=description,
        workplace_type=WorkplaceType.REMOTE,
        locations=[
            JobLocation(
                label="Remote — United States",
                country_code="US",
                is_primary=True,
                is_remote=True,
            )
        ],
        compensation=extract_compensation_from_text(description),
        job_url=record["job_url"],
    )


def evaluate_calibration_v2(
    profile: CareerProfile,
    path: str | Path,
) -> CalibrationV2Report:
    records = load_calibration_v2(path)
    counts = {"great": 0, "maybe": 0, "wrong": 0, "duplicate": 0}
    positives_visible = 0
    wrong_filtered = 0
    disagreements = []
    for record in records:
        classification = record["human"]["classification"]
        counts[classification] += 1
        result = score_job(profile, calibration_job(record))
        family = matched_role_family(profile, record["exact_job_title"])
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
                }
            )
    positive_total = counts["great"] + counts["maybe"]
    return CalibrationV2Report(
        total=len(records),
        **counts,
        positives_visible=positives_visible,
        wrong_filtered=wrong_filtered,
        positive_recall=round(100 * positives_visible / positive_total, 2),
        wrong_rejection_rate=round(100 * wrong_filtered / counts["wrong"], 2),
        disagreements=tuple(disagreements),
    )
