"""Draw a stratified sample of Gateway 1 rejections for human labelling.

Gateway 1 rejects roughly 60% of the corpus, and a false rejection there is
invisible: the job scores 0, nobody sees it, and the feedback loop can never
correct it. The only way to know the error rate is to look.

The output is deliberately shaped as labelling input rather than a report. Each
record carries the exact inputs the resolver saw -- raw label, country_code,
workplace_type, and the posting's own words about location -- so a human verdict
becomes a deterministic input/expected-output case. Once labelled, the file
becomes a pinned corpus and a CI gate, the same way the matching corpus works.

Strata exist because the failure modes are not uniformly distributed. Sampling
100 rows at random would be mostly obvious foreign rejections and would say
nothing about the placeholder or ambiguous-city cases that actually hurt.

Read-only: it scores in memory and writes nothing back.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from collections import defaultdict
from html import escape
from pathlib import Path

from ferminator.matching import score_job
from ferminator.repository import PostgresRepository

PLACEHOLDER = re.compile(r"\d+\s+locations?|all locations?|unspecified|various", re.I)
REMOTE = re.compile(r"\bremote\b|work from home|anywhere", re.I)
US_WORD = re.compile(r"\b(usa|u\.s\.a?|united states)\b|^\s*us\.?\s*$", re.I)
STATE = re.compile(r",\s*(A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]"
                   r"|N[CDEHJMVY]|O[HKR]|P[A]|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b")
FOREIGN = re.compile(r"canada|united kingdom|\buk\b|london|india|germany|france|spain"
                     r"|singapore|japan|australia|brazil|mexico|poland|ireland|emea|apac",
                     re.I)
# A location sentence is worth more to a labeller than the whole description.
LOCATION_SENTENCE = re.compile(
    r"[^.\n]{0,180}(?:remote|hybrid|on-?site|located|location|relocat|based in|"
    r"work from|office|eligible to work|authorized to work)[^.\n]{0,180}", re.I)


def stratum(label: str) -> str:
    """Bucket a rejection by the reason it is interesting, most specific first."""
    if not label.strip():
        return "empty_label"
    if PLACEHOLDER.search(label):
        return "unparseable_placeholder"
    if US_WORD.search(label) or STATE.search(label):
        return "claims_us"
    if REMOTE.search(label) and FOREIGN.search(label):
        return "remote_but_foreign"
    if REMOTE.search(label):
        return "remote_unqualified"
    if FOREIGN.search(label):
        return "clearly_foreign"
    if "|" in label or ";" in label or "," in label:
        return "multi_or_city_label"
    return "bare_token"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260729)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = PostgresRepository(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        profile = next(
            candidate
            for _id, candidate in repository.scannable_profiles()
            if candidate.profile.slug == args.slug
        )
        jobs = repository.active_jobs()
    finally:
        repository.close()

    buckets: dict[str, list] = defaultdict(list)
    for _job_id, _rev, job in jobs:
        result = score_job(profile, job)
        if result.eligible or "geography rejected" not in (result.explanation or ""):
            continue
        label = " | ".join(location.label for location in job.locations)
        buckets[stratum(label)].append((job, label, result))

    rng = random.Random(args.seed)
    per = max(1, args.size // max(1, len(buckets)))
    chosen: list = []
    for name in sorted(buckets):
        rows = buckets[name]
        rng.shuffle(rows)
        chosen.extend((name, *row) for row in rows[:per])
    rng.shuffle(chosen)
    chosen = chosen[: args.size]

    total = sum(len(v) for v in buckets.values())
    lines = [
        "# Geography rejections — labelling sample",
        "",
        f"Profile: {args.slug} · sample {len(chosen)} of {total} geography rejections",
        f"Deterministic seed: {args.seed}",
        "",
        "Gateway 1 rejects these before any other rule runs, so a wrong call here is",
        "invisible: the job scores 0, never appears, and no rating can correct it.",
        "",
        "## How to label",
        "",
        "For each record set `<verdict>` to exactly one of:",
        "",
        "- `CORRECT_REJECT` — genuinely not reachable for a US-based remote-or-Bend candidate",
        "- `WRONG_REJECT` — this is US-reachable and should have been scored",
        "- `UNKNOWABLE` — the posting genuinely does not say where the work is",
        "",
        "Judge only the location question. Ignore whether the role suits Adam; a",
        "wrongly-rejected job we do not want is still a resolver bug.",
        "",
        "Add `<note>` when the reason is not obvious from the label alone.",
        "",
        "## Strata present",
        "",
        "| Stratum | In corpus | Sampled |",
        "|---|---:|---:|",
    ]
    sampled_counts: dict[str, int] = defaultdict(int)
    for name, *_ in chosen:
        sampled_counts[name] += 1
    for name in sorted(buckets):
        lines.append(f"| {name} | {len(buckets[name])} | {sampled_counts.get(name, 0)} |")
    lines += ["", "---", "", "<geography_sample>"]

    for index, (name, job, label, result) in enumerate(chosen, start=1):
        countries = ",".join(
            sorted({loc.country_code or "" for loc in job.locations if loc.country_code})
        )
        snippets = LOCATION_SENTENCE.findall(job.description_text or "")[:3]
        lines += [
            "",
            f'<record id="{index}" stratum="{escape(name, quote=True)}">',
            f"  <company>{escape(job.company_name)}</company>",
            f"  <job_title>{escape(job.title)}</job_title>",
            f"  <provider>{job.provider.value}</provider>",
            "  <resolver_input>",
            f"    <raw_location_label>{escape(label) or '(empty)'}</raw_location_label>",
            f"    <country_code>{escape(countries) or '(null)'}</country_code>",
            f"    <workplace_type>{job.workplace_type.value}</workplace_type>",
            "  </resolver_input>",
            "  <posting_says_about_location><![CDATA[",
            "\n".join(f"    - {' '.join(s.split())}" for s in snippets) or "    (nothing found)",
            "  ]]></posting_says_about_location>",
            "  <ferminator_decision>REJECTED — "
            f"{escape(result.concerns[0] if result.concerns else '')}</ferminator_decision>",
            f"  <job_url>{escape(str(job.job_url))}</job_url>",
            "  <verdict></verdict>",
            "  <note></note>",
            "</record>",
        ]
    lines += ["", "</geography_sample>", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"sampled": len(chosen), "population": total,
                      "strata": {k: len(v) for k, v in sorted(buckets.items())}}, indent=1))


if __name__ == "__main__":
    main()
