"""Pull lane-relevant jobs from remote-first job feeds and filter them.

Sources (public JSON APIs, no auth):
  - Remotive:  https://remotive.com/api/remote-jobs?search=<term>
  - RemoteOK:  https://remoteok.com/api  (single feed, filtered locally)

Every find is normalized to the shape check_aggregator_finds.py expects and
piped through it, so verdict fingerprints, applied history, ATS-pipeline
overlap, and the title gate all apply before anything reaches Adam.

Output: a ready-to-append Markdown section on stdout (empty string when
nothing survives), diagnostics on stderr.

Requires DATABASE_URL in the environment (the daily task provides it the same
way it does for the export).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Ferminator/1.0 remote-feeds"}
ROOT = Path(__file__).resolve().parents[1]

# One query per lane family; the title gate downstream does the fine sorting.
REMOTIVE_TERMS = [
    "copywriter", "copy lead", "AI enablement", "AI adoption",
    "applied AI", "prompt engineer", "SEO strategist", "AEO",
    "content strategist",
]
REMOTEOK_PATTERN = re.compile(
    r"copywrit|copy lead|ai enablement|ai adoption|applied ai|prompt engineer"
    r"|seo|aeo|content strateg", re.I,
)
# US-friendly location markers; feeds carry worldwide listings.
US_OK = re.compile(
    r"\b(usa|us only|united states|north america|americas|worldwide|anywhere)\b", re.I
)


def fetch(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def collect() -> list[dict]:
    finds: list[dict] = []
    for term in REMOTIVE_TERMS:
        try:
            data = fetch(f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(term)}&limit=50")
        except Exception as exc:
            print(f"remotive {term!r}: {type(exc).__name__}", file=sys.stderr)
            continue
        for job in data.get("jobs", []):
            region = job.get("candidate_required_location", "")
            if region and not US_OK.search(region):
                continue
            finds.append({
                "company": job.get("company_name", ""),
                "title": job.get("title", ""),
                "url": job.get("url", ""),
                "salary": job.get("salary") or "",
                "location": region or "remote",
                "source": "remotive",
            })
    try:
        for job in fetch("https://remoteok.com/api"):
            if not isinstance(job, dict) or "position" not in job:
                continue
            haystack = f"{job.get('position', '')} {' '.join(job.get('tags', []))}"
            if not REMOTEOK_PATTERN.search(haystack):
                continue
            region = job.get("location", "")
            if region and not US_OK.search(region):
                continue
            finds.append({
                "company": job.get("company", ""),
                "title": job.get("position", ""),
                "url": job.get("url", ""),
                "salary": (f"{job.get('salary_min')}-{job.get('salary_max')}"
                           if job.get("salary_min") else ""),
                "location": region or "remote",
                "source": "remoteok",
            })
    except Exception as exc:
        print(f"remoteok: {type(exc).__name__}", file=sys.stderr)

    unique: dict[tuple[str, str], dict] = {}
    for find in finds:
        unique.setdefault(
            (find["company"].casefold().strip(), find["title"].casefold().strip()), find
        )
    return list(unique.values())


def main() -> None:
    finds = collect()
    print(f"collected {len(finds)} raw finds", file=sys.stderr)
    checker = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_aggregator_finds.py")],
        input=json.dumps(finds), capture_output=True, text=True, env=os.environ,
    )
    print(checker.stderr.strip(), file=sys.stderr)
    if checker.returncode != 0:
        raise SystemExit(f"checker failed: {checker.stderr.strip()[:300]}")
    kept = json.loads(checker.stdout)
    if not kept:
        print("")
        return
    lines = [
        "",
        "## Remote-feed finds (Remotive / RemoteOK)",
        "",
        "New since last run, deduped against verdicts, applied history, and the",
        "ATS pipeline. Aggregator stubs: verify details on the posting itself.",
        "",
    ]
    for find in kept:
        salary = f" · {find['salary']}" if find.get("salary") else ""
        lines.append(
            f"- **{find['company']}** — {find['title']}{salary} · {find['location']} "
            f"· [{find['source']}]({find['url']})"
        )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
