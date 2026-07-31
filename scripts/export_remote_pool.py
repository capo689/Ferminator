"""Run the remote-only funnel backlog and write the review pool to Markdown.

Stages, in the framework's precedence order:

    1. already applied or suppressed   (job_history, the shared predicate)
    2. remote, verified against the body
    3. title exclusions, then title inclusion

Everything that survives is written with its full job description. Everything
rejected is written to a companion file with the rule that rejected it, so a
silent drop is impossible to hide.

Deliberately does not read for fit, salary, or seniority. That is the final
pass, done by hand for now.

Usage:

    DATABASE_URL=... python scripts/export_remote_pool.py \\
        --profile adam-cagle --out-dir ~/Documents/ferminator-review
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from ferminator.repository import SUPPRESSED_BY_HISTORY_SQL
from ferminator.search_framework import (
    ALL_INCLUDE_TERMS,
    classify_remote,
    classify_title,
)

# Cheap title prefilter, pushed into SQL so we do not drag 63,000 full job
# descriptions across the wire to throw almost all of them away. Built from the
# module's own include lists so it cannot drift out of step with the real gate,
# and deliberately looser than that gate: it only has to avoid discarding
# anything `classify_title` would keep. Python stays authoritative.
_PREFILTER = "|".join(
    sorted({re.escape(term.split(",")[0].strip()) for term in ALL_INCLUDE_TERMS})
).replace(r"\ ", r"\s+")

# Candidate rows. The history suppression is applied here, in SQL, using the
# same constant `web_matches` uses. It is not restated.
QUERY = f"""
with p as (select id from public.profiles where slug = %s)
select
  j.id, j.title, j.company_name, j.workplace_type,
  coalesce(j.apply_url, j.job_url) as url,
  j.salary_min, j.salary_max, j.salary_currency,
  j.first_seen_at, j.published_at,
  coalesce((
    select string_agg(l.label, ' | ' order by l.is_primary desc)
    from public.job_locations l where l.job_id = j.id
  ), '') as location_labels,
  coalesce((
    select bool_or(l.is_remote) from public.job_locations l where l.job_id = j.id
  ), false) as any_location_flagged_remote,
  coalesce(r.description_text, '') as description
from public.jobs j
cross join p
left join public.job_revisions r on r.id = j.current_revision_id
where j.active
  and j.title ~* %s
  and not exists ({SUPPRESSED_BY_HISTORY_SQL})
  -- Reviewed means reviewed: any recorded verdict, keeper or rejection,
  -- keeps a job out of every future pool. The 2026-07-29 backlog pass
  -- recorded all 721, so from here each run is new arrivals only.
  and not exists (
    select 1 from public.match_feedback f
    where f.profile_id = p.id and f.job_id = j.id
  )
order by j.company_name, j.title
"""

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_BLANK = re.compile(r"\n{3,}")


def to_text(html: str) -> str:
    """Flatten stored HTML to readable text without collapsing structure."""
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6])\s*/?>", "\n", html)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", text)
    text = _TAG.sub("", text)
    for entity, char in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&mdash;", ", "), ("&ndash;", ", "),
    ):
        text = text.replace(entity, char)
    text = _WS.sub(" ", text)
    return _BLANK.sub("\n\n", text).strip()


def salary_line(row: dict) -> str:
    low, high = row.get("salary_min"), row.get("salary_max")
    if not low and not high:
        return "not stated in structured data, check the description"
    unit = row.get("salary_currency") or "USD"
    if low and high:
        return f"{low:,.0f} - {high:,.0f} {unit}"
    return f"{(low or high):,.0f} {unit}"


def render(jobs: list[dict], part: int, total_parts: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"# Ferminator Review Pool — part {part} of {total_parts}",
        "",
        f"Generated {stamp}. {len(jobs)} jobs in this file.",
        "",
        "Every job here is remote (verified against the description, not just the",
        "title), matches a title keyword, survives every title exclusion, and is not",
        "already applied for or suppressed.",
        "",
        "Not yet judged: fit, seniority, salary, or hard requirements. That is the pass",
        "you are about to run.",
        "",
        "<review_pool>",
    ]
    for index, job in enumerate(jobs, start=1):
        out += [
            "",
            f'<job index="{index}" id="{escape(str(job["id"]), quote=True)}">',
            f"  <company>{escape(job['company_name'] or '')}</company>",
            f"  <job_title>{escape(job['title'] or '')}</job_title>",
            f"  <title_match group=\"{escape(job['_group'] or '')}\">"
            f"{escape(job['_matched'] or '')}</title_match>",
            f"  <remote_evidence>{escape(job['_remote_reason'])}</remote_evidence>",
            f"  <location>{escape(job['location_labels'] or 'not stated')}</location>",
            f"  <salary_structured>{escape(salary_line(job))}</salary_structured>",
            f"  <url>{escape(job['url'] or '')}</url>",
            "  <complete_job_description><![CDATA[",
            to_text(job["description"]).replace("]]>", "]] >"),
            "  ]]></complete_job_description>",
            "</job>",
        ]
    out += ["", "</review_pool>", ""]
    return "\n".join(out)


def render_rejects(rows: list[tuple[str, str, str]]) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# Ferminator — rejected by the funnel",
        "",
        f"Generated {stamp}. {len(rows)} jobs, with the rule that rejected each one.",
        "Here so that nothing is dropped silently and the gates stay auditable.",
        "",
        "| company | title | rejected by |",
        "| --- | --- | --- |",
    ]
    for company, title, reason in rows:
        clean = lambda s: (s or "").replace("|", "\\|")  # noqa: E731
        out.append(f"| {clean(company)} | {clean(title)} | {clean(reason)} |")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="adam-cagle")
    parser.add_argument("--out-dir", type=Path, required=True)
    # One file is the default. The split existed for the 721-job backlog
    # pass; a daily pool of a few dozen jobs never needs it.
    parser.add_argument("--parts", type=int, default=1)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is not set. Export it or pass --database-url.")

    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        rows = conn.execute(QUERY, (args.profile, _PREFILTER)).fetchall()
    print(f"candidates after history suppression: {len(rows)}")

    kept: list[dict] = []
    rejected: list[tuple[str, str, str]] = []

    for row in rows:
        body = to_text(row["description"])

        remote = classify_remote(
            title=row["title"] or "",
            location_labels=row["location_labels"] or "",
            description=body,
            workplace_type=row["workplace_type"],
            any_location_flagged_remote=row["any_location_flagged_remote"],
        )
        if not remote.is_remote:
            continue  # 13k+ of these; listing them would drown the reject file

        title = classify_title(row["title"] or "")
        if not title.included:
            rejected.append((row["company_name"], row["title"], title.excluded_by or "?"))
            continue

        row["_group"] = title.group
        row["_matched"] = title.matched
        row["_remote_reason"] = remote.reason
        kept.append(row)

    print(f"remote: {len(kept) + len(rejected)}")
    print(f"rejected on title: {len(rejected)}")
    print(f"KEPT: {len(kept)}")

    # Local date, not UTC: an evening run in Oregon is not tomorrow's file.
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    parts = max(1, args.parts)
    size = -(-len(kept) // parts)
    for index in range(parts):
        chunk = kept[index * size : (index + 1) * size]
        if not chunk:
            continue
        path = args.out_dir / f"ferminator-review-pool-{stamp}-part{index + 1}.md"
        path.write_text(render(chunk, index + 1, parts), encoding="utf-8")
        print(f"wrote {path} ({len(chunk)} jobs, {path.stat().st_size // 1024} KB)")

    path = args.out_dir / f"ferminator-rejected-on-title-{stamp}.md"
    path.write_text(render_rejects(rejected), encoding="utf-8")
    print(f"wrote {path} ({len(rejected)} jobs)")


if __name__ == "__main__":
    main()
