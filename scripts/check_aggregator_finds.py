"""Filter aggregator job finds against everything Ferminator already knows.

Input on stdin: a JSON array of {"company": ..., "title": ..., "url": ...,
"salary_min": ..., "source": ...} objects, as collected from the Indeed, Dice,
and ZipRecruiter connectors.

A find survives only if ALL of these hold:
  - its company+title fingerprint has no recorded verdict (reviewed is reviewed,
    same rule as the ATS pool)
  - it is not suppressed or applied-to in job_history
  - it is not already an active tracked job (the ATS pipeline will surface it
    with a full JD, which is strictly better than an aggregator stub)
  - its title passes the same include/exclude gate as everything else

Output on stdout: the surviving finds as JSON, each annotated with its title
match, plus a summary of what was dropped and why on stderr.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ferminator.search_framework import classify_title  # noqa: E402

QUERY = """
with cand(company, title) as (select * from jsonb_to_recordset(%s::jsonb)
                              as t(company text, title text)),
p as (select id from public.profiles where slug = %s)
select c.company, c.title,
  exists (
    select 1 from public.match_feedback f
    join public.jobs jf on jf.id = f.job_id, p
    where f.profile_id = p.id
      and public.normalize_job_part(jf.company_name) = public.normalize_job_part(c.company)
      and public.normalize_job_part(jf.title) = public.normalize_job_part(c.title)
  ) as has_verdict,
  exists (
    select 1 from public.job_history h, p
    where h.profile_id = p.id
      and (h.permanent or h.suppress_until > now())
      and h.fingerprint = public.normalize_job_part(c.company)
        || '::' || public.normalize_job_part(c.title)
  ) as suppressed,
  exists (
    select 1 from public.jobs j
    where j.active
      and public.normalize_job_part(j.company_name) = public.normalize_job_part(c.company)
      and public.normalize_job_part(j.title) = public.normalize_job_part(c.title)
  ) as already_tracked
from cand c
"""


def main() -> None:
    finds = json.load(sys.stdin)
    if not finds:
        print("[]")
        return
    pairs = [{"company": f.get("company", ""), "title": f.get("title", "")} for f in finds]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(QUERY, (json.dumps(pairs), "adam-cagle")).fetchall()
    flags = {(r[0], r[1]): {"has_verdict": r[2], "suppressed": r[3], "already_tracked": r[4]}
             for r in rows}

    kept, dropped = [], {"reviewed": 0, "suppressed/applied": 0,
                         "already in ATS pipeline": 0, "title gate": 0}
    for find in finds:
        flag = flags.get((find.get("company", ""), find.get("title", "")), {})
        if flag.get("has_verdict"):
            dropped["reviewed"] += 1
            continue
        if flag.get("suppressed"):
            dropped["suppressed/applied"] += 1
            continue
        if flag.get("already_tracked"):
            dropped["already in ATS pipeline"] += 1
            continue
        verdict = classify_title(find.get("title", ""))
        if not verdict.included:
            dropped["title gate"] += 1
            continue
        kept.append({**find, "title_match": verdict.matched, "title_group": verdict.group})

    json.dump(kept, sys.stdout, indent=2)
    print(f"\nkept {len(kept)} of {len(finds)}; dropped: "
          + ", ".join(f"{v} {k}" for k, v in dropped.items() if v), file=sys.stderr)


if __name__ == "__main__":
    main()
