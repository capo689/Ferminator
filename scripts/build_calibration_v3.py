#!/usr/bin/env python3
"""Merge Calibration V2 with the second reviewed Discover batch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

SECTION_PATTERN = re.compile(r"(?m)^##\s+(?=\d+\.\s)")
HEADING_PATTERN = re.compile(r"^(\d+)\.\s+(.+)")
LISTING_PATTERN = re.compile(r"\*\*Original listing:\*\* \[Open role\]\((https?://[^)]+)\)")
COMPANY_PATTERN = re.compile(r"\*\*Company:\*\*\s*(.+)")
SCHEMA_VERSION = "ferminator_calibration_v3"


def _sections(markdown: str) -> dict[str, str]:
    result = {}
    for section in SECTION_PATTERN.split(markdown)[1:]:
        heading = HEADING_PATTERN.match(section)
        if heading:
            result[heading.group(1)] = section
    return result


def _body_between(section: str, start: str, end: str | None = None) -> str:
    if start not in section:
        return ""
    body = section.split(start, 1)[1]
    if end and end in body:
        body = body.split(end, 1)[0]
    return body.strip()


def build(base_path: Path, csv_path: Path, markdown_path: Path) -> list[dict]:
    base = [json.loads(line) for line in base_path.read_text().splitlines() if line.strip()]
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    sections = _sections(markdown_path.read_text(encoding="utf-8"))
    if len(base) != 61 or len(rows) != 24 or len(sections) != 24:
        raise ValueError(
            "Expected 61 base records and 24 reviewed CSV/Markdown jobs; "
            f"got {len(base)}, {len(rows)}, and {len(sections)}"
        )

    records = []
    for index, record in enumerate(base, 1):
        records.append(
            {
                **record,
                "schema_version": SCHEMA_VERSION,
                "record_id": f"calibration-v3-{index:03d}",
                "job_number": index,
                "source_batch": "discover-reviewed-2026-07-26-a",
                "source_job_number": record["job_number"],
            }
        )

    for row in rows:
        source_number = row["job_number"].strip()
        section = sections.get(source_number)
        if section is None:
            raise ValueError(f"Missing Markdown section for job {source_number}")
        heading = HEADING_PATTERN.match(section)
        listing = LISTING_PATTERN.search(section)
        company = COMPANY_PATTERN.search(section)
        if not heading or not listing or not company:
            raise ValueError(f"Incomplete Markdown metadata for job {source_number}")
        if heading.group(2).strip() != row["job_title"].strip():
            raise ValueError(f"Title disagreement for job {source_number}")
        if company.group(1).strip() != row["company"].strip():
            raise ValueError(f"Company disagreement for job {source_number}")
        classification = row["classification"].strip().casefold()
        if classification not in {"great", "maybe", "wrong", "duplicate"}:
            raise ValueError(
                f"Unsupported classification for job {source_number}: {classification}"
            )
        description = _body_between(
            section,
            "### Full job description",
            "### JD Review",
        )
        review = _body_between(section, "### JD Review")
        if classification != "duplicate" and not description:
            raise ValueError(f"Missing full description for job {source_number}")
        number = len(records) + 1
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_id": f"calibration-v3-{number:03d}",
                "job_number": number,
                "source_batch": "discover-unrated-reviewed-2026-07-26-b",
                "source_job_number": int(source_number),
                "company": row["company"].strip(),
                "exact_job_title": row["job_title"].strip(),
                "job_url": listing.group(1),
                "full_job_description": description,
                "human": {
                    "classification": classification,
                    "reason": row["pass_reason"].strip(),
                    "long_form_review": review,
                },
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = build(args.base, args.csv, args.markdown)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    args.output.write_text(serialized, encoding="utf-8")
    print(f"Wrote {len(records)} records to {args.output}")
    print(f"SHA256 {hashlib.sha256(serialized.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
