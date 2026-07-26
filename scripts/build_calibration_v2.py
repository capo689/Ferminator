#!/usr/bin/env python3
"""Build the reviewed Ferminator V2 calibration corpus from CSV + Markdown."""

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


def _sections(markdown: str) -> dict[str, str]:
    result: dict[str, str] = {}
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


def build(csv_path: Path, markdown_path: Path) -> list[dict]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    sections = _sections(markdown_path.read_text(encoding="utf-8"))
    if len(rows) != 61 or len(sections) != 61:
        raise ValueError(
            f"Expected 61 CSV rows and Markdown sections; got {len(rows)} and {len(sections)}"
        )

    records = []
    for row in rows:
        number = row["job_number"].strip()
        section = sections.get(number)
        if section is None:
            raise ValueError(f"Missing Markdown section for job {number}")
        heading = HEADING_PATTERN.match(section)
        listing = LISTING_PATTERN.search(section)
        company = COMPANY_PATTERN.search(section)
        if not heading or not listing or not company:
            raise ValueError(f"Incomplete Markdown metadata for job {number}")
        if heading.group(2).strip() != row["job_title"].strip():
            raise ValueError(f"Title disagreement for job {number}")
        if company.group(1).strip() != row["company"].strip():
            raise ValueError(f"Company disagreement for job {number}")

        classification = row["classification"].strip().casefold()
        if classification not in {"great", "maybe", "wrong", "duplicate"}:
            raise ValueError(f"Unsupported classification for job {number}: {classification}")
        description = _body_between(
            section,
            "### Full job description",
            "### JD Review",
        )
        review = _body_between(section, "### JD Review")
        if classification not in {"duplicate"} and not description:
            raise ValueError(f"Missing full description for job {number}")

        records.append(
            {
                "schema_version": "ferminator_calibration_v2",
                "record_id": f"reviewed-2026-07-26-{int(number):02d}",
                "job_number": int(number),
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
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = build(args.csv, args.markdown)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records
    )
    args.output.write_text(serialized, encoding="utf-8")
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    print(f"Wrote {len(records)} records to {args.output}")
    print(f"SHA256 {digest}")


if __name__ == "__main__":
    main()
