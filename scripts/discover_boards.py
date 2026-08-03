"""Probe companies for public ATS boards across the providers Ferminator speaks.

Input: newline-separated company names on stdin (parenthetical suffixes are
stripped for slug generation but kept for display).

For each company, a handful of slug candidates are derived from the name and
probed against each provider's public jobs endpoint. A probe counts as a hit
only when the response is valid JSON shaped like that provider's job listing
payload, so a marketing page or a soft-404 does not qualify.

Output: JSON records {company, provider, board_key, source_url, jobs} for every
hit, one per company/provider (first slug that answers wins), plus a miss list.
Read-only; adding hits to the registry is a separate, deliberate step.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Ferminator/1.0 board-discovery"}
TIMEOUT = 12


def fetch_json(url: str):
    request = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read(2_000_000)
    return json.loads(body)


def probe_greenhouse(slug):
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    jobs = data.get("jobs")
    if isinstance(jobs, list):
        return len(jobs), f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def probe_lever(slug):
    data = fetch_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if isinstance(data, list):
        return len(data), f"https://jobs.lever.co/{slug}"


def probe_ashby(slug):
    data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = data.get("jobs")
    if isinstance(jobs, list):
        return len(jobs), f"https://jobs.ashbyhq.com/{slug}"


def probe_workable(slug):
    data = fetch_json(f"https://www.workable.com/api/accounts/{slug}?details=true")
    jobs = data.get("jobs")
    if isinstance(jobs, list):
        return len(jobs), f"https://apply.workable.com/{slug}"


def probe_smartrecruiters(slug):
    data = fetch_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings")
    content = data.get("content")
    if isinstance(content, list):
        return len(content), f"https://careers.smartrecruiters.com/{slug}"


def probe_breezy(slug):
    data = fetch_json(f"https://{slug}.breezy.hr/json")
    if isinstance(data, list):
        return len(data), f"https://{slug}.breezy.hr"


PROVIDERS = {
    "greenhouse": probe_greenhouse,
    "lever": probe_lever,
    "ashby": probe_ashby,
    "workable": probe_workable,
    "smartrecruiters": probe_smartrecruiters,
    "breezy": probe_breezy,
}


def slug_candidates(name: str) -> list[str]:
    base = re.sub(r"\s*\(.*?\)", "", name).strip()
    base = base.split("/")[0].strip()
    lower = base.lower()
    plain = re.sub(r"[^a-z0-9]", "", lower)
    hyphen = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    nodot = re.sub(r"\.(com|io|ai)$", "", lower)
    nodot_plain = re.sub(r"[^a-z0-9]", "", nodot)
    first = lower.split()[0] if lower.split() else lower
    first_plain = re.sub(r"[^a-z0-9]", "", first)
    seen, out = set(), []
    for candidate in (plain, hyphen, nodot_plain, first_plain):
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def probe_company(name: str):
    hits = []
    for provider, probe in PROVIDERS.items():
        for slug in slug_candidates(name):
            try:
                result = probe(slug)
            except Exception:
                continue
            if result:
                jobs, url = result
                hits.append({"company": name, "provider": provider,
                             "board_key": slug, "source_url": url, "jobs": jobs})
                break  # first working slug per provider is enough
    return name, hits


def main() -> None:
    names = [line.strip() for line in sys.stdin if line.strip()]
    all_hits, misses = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, hits in pool.map(probe_company, names):
            if hits:
                all_hits.extend(hits)
            else:
                misses.append(name)
            found = ", ".join(f"{h['provider']}({h['jobs']})" for h in hits) or "no board found"
            print(f"{name:35} {found}", file=sys.stderr)
    json.dump({"hits": all_hits, "misses": misses}, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
