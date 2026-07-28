"""Report where a profile's matches die, without writing anything.

Scores every active job in memory and counts the gateway that rejected each
one, so a change to the matcher can be measured against the live corpus before
it is allowed to touch stored matches.

Read-only: it opens the database, reads jobs, and writes nothing back.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from pathlib import Path

from ferminator.matching import score_job
from ferminator.profiles import load_profile
from ferminator.repository import PostgresRepository


def _gateway(result) -> str:
    explanation = result.explanation or ""
    if result.eligible:
        return "eligible"
    for marker, label in (
        ("on-site requirement", "1b on-site"),
        ("Gateway 1", "1 geography"),
        ("Gateway 2", "2 title/function"),
        ("Gateway 3", "3 disqualifier"),
        ("Gateway 4", "4 compensation"),
        ("Gateway 5", "5 score floor"),
    ):
        if marker in explanation:
            return label
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser()
    # Accounts provisioned through /admin exist only as a database row, so a
    # file path cannot reach them. Taking a slug keeps this usable for every
    # account rather than only the one profile that still lives on disk.
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--slug")
    parser.add_argument("--samples", type=int, default=25)
    args = parser.parse_args()
    if not args.profile and not args.slug:
        parser.error("pass --profile or --slug")

    database_url = os.environ["DATABASE_URL"]
    repository = PostgresRepository(database_url, min_size=1, max_size=2)
    try:
        if args.profile:
            profile = load_profile(args.profile)
        else:
            matches = [
                candidate
                for _id, candidate in repository.scannable_profiles()
                if candidate.profile.slug == args.slug
            ]
            if not matches:
                raise SystemExit(f"no scannable profile with slug {args.slug!r}")
            profile = matches[0]
        jobs = repository.active_jobs()
    finally:
        repository.close()

    gateways: Counter[str] = Counter()
    eligible: list[tuple[float, str, str]] = []
    for _job_id, _revision_id, job in jobs:
        result = score_job(profile, job)
        gateways[_gateway(result)] += 1
        if result.eligible:
            eligible.append((result.score, job.title, job.company_name))

    total = sum(gateways.values())
    print(f"profile={profile.profile.slug} active_jobs={total}")
    print("\n--- where jobs are rejected ---")
    for name, count in sorted(gateways.items()):
        print(f"{name:22} {count:>7}  {100 * count / total:5.1f}%")

    eligible.sort(reverse=True)
    print(f"\neligible={len(eligible)}")
    for floor in (40, 50, 60, 70):
        print(f"  score >= {floor}: {sum(1 for s, _, _ in eligible if s >= floor)}")

    print(f"\n--- top {args.samples} by score ---")
    for score, title, company in eligible[: args.samples]:
        print(f"{score:6.1f}  {company[:32]:32} {title[:60]}")


if __name__ == "__main__":
    main()
