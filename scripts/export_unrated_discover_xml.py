"""Export the live default Discover view's unrated jobs as XML-tagged Markdown."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from ferminator.discover_visibility import apply_role_thresholds, sort_discover_matches
from ferminator.freshness import annotate_freshness, apply_default_freshness_policy
from ferminator.profiles import load_profile
from ferminator.repository import PostgresRepository


def _cdata(value: str) -> str:
    return value.replace("]]>", "]]]]><![CDATA[>")


def _source_description(item: dict) -> str:
    stored = (item.get("compensation_text") or "").strip()
    if stored:
        return stored
    source_url = item.get("apply_url")
    if not source_url:
        return ""
    request = Request(source_url, headers={"User-Agent": "Ferminator/1.0"})
    with urlopen(request, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if isinstance(record, dict) and record.get("@type") == "JobPosting":
                return str(record.get("description") or "").strip()
    description = soup.select_one(".position-description .description")
    return str(description) if description else ""


def _discover_matches(
    database_url: str,
    profile_path: Path,
    scope: str = "discover",
) -> list[dict]:
    """Collect a profile's unrated matches.

    `discover` mirrors exactly what the page shows: role-family visibility
    floors and the default freshness policy both applied. `all-eligible` keeps
    every unrated job that is still sticky-eligible, which is a far larger set,
    for a full review pass rather than a daily one.
    """
    profile = load_profile(profile_path)
    repository = PostgresRepository(database_url, min_size=1, max_size=2)
    try:
        matches = repository.web_matches(profile.profile.slug, minimum_score=0, limit=10000)
        thresholds = repository.role_thresholds(profile.profile.slug)
    finally:
        repository.close()
    print(f"live_eligible={len(matches)}")

    if scope == "discover":
        matches = apply_role_thresholds(profile, matches, thresholds)
        print(f"after_role_thresholds={len(matches)}")
    matches = annotate_freshness(matches)
    matches = [
        item
        for item in matches
        if item.get("feedback_verdict") is None
    ]
    print(f"after_unrated_only={len(matches)}")
    if scope == "discover":
        matches = apply_default_freshness_policy(matches)
        print(f"after_freshness={len(matches)}")

    return sort_discover_matches(matches, "relevance")


def _render(matches: list[dict]) -> str:
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    descriptions = [_source_description(item) for item in matches]
    complete = sum(bool(description) for description in descriptions)
    lines = [
        "# Ferminator Discover — Unrated Full Job Descriptions",
        "",
        f"Generated: {generated}",
        f"Unrated jobs: {len(matches)}",
        f"Jobs with complete descriptions: {complete}",
        "",
        "<discover_jobs>",
    ]

    for index, (item, description) in enumerate(zip(matches, descriptions), start=1):
        status = "complete" if description else "unavailable"
        lines.extend(
            [
                "",
                f'<job index="{index}" id="{escape(str(item["id"]), quote=True)}">',
                f"  <company>{escape(str(item['company']))}</company>",
                f"  <job_title>{escape(str(item['title']))}</job_title>",
                f'  <complete_job_description status="{status}"><![CDATA[',
                _cdata(description),
                "]]></complete_job_description>",
                "</job>",
            ]
        )

    lines.extend(["", "</discover_jobs>", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--scope",
        choices=("discover", "all-eligible"),
        default="discover",
        help="discover mirrors the page; all-eligible keeps every unrated match.",
    )
    args = parser.parse_args()

    matches = _discover_matches(args.database_url, args.profile, args.scope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_render(matches), encoding="utf-8")
    print(f"exported={len(matches)} output={args.output}")


if __name__ == "__main__":
    main()
