# ATS Directory and Bulk Ingestion

Status: Implemented
Validated: 2026-07-25

## Source policy

The protected Supabase registry is the runtime source of truth. A board is
admitted only after its official public ATS endpoint returns a structurally
valid feed with at least one current job. The master registry and validation
evidence are proprietary operational data and must never be committed to the
public repository.

## Keeping the directory current

Every twice-daily scan:

1. reads enabled sources from protected `companies` and `ats_boards` tables;
2. fetches every enabled source through its production adapter;
3. records validation time, last success, consecutive failures, and a safe
   error code;
4. marks a source degraded after a failure and failed after three consecutive
   failures;
5. removes failed sources from the user-facing directory while continuing to
   retry them on subsequent scans;
6. restores a recovered source to healthy automatically after a successful
   scan.

To evaluate an updated saved HTML or CSV master list before changing the
registry:

```bash
ferminator directory-check /private/master-list.html \
  --workers 8 \
  --json-output /private/board-validation-YYYY-MM-DD.json
```

The command exits non-zero if any source is unreachable, malformed, or empty.
Use `directory-merge` with private JSON evidence and a private registry export,
then use `registry-import` to update Supabase. Never commit those artifacts.

## Bulk-ingestion design

The previous scan fetched boards serially. At 54 sources that took about 25.5
minutes and left almost no room under the 30-minute GitHub Actions limit.

The scan now uses a bounded two-phase pipeline:

1. Up to eight worker threads fetch and normalize independent public boards in
   parallel without holding database connections.
2. Successful payloads are applied with existing lifecycle, idempotency,
   mass-removal, revision, and transaction safeguards.
3. A failed source is isolated and recorded without discarding successful
   sources.
4. Existing revision hashes are loaded once per board. Unchanged jobs receive
   one set-based freshness update; only new or materially changed jobs execute
   revision and location upserts.
5. Matching is refreshed once after all ingestion work, rather than per board.

The final 69-board source validation completed in 2.8 seconds. A separate live
bulk test of all 113 enabled directory boards fetched and normalized 8,625 jobs
in 10.4 seconds with eight workers and zero source failures. The production
workflow retains its 30-minute ceiling as a performance guard; broadening the
registry no longer consumes that budget linearly in network wait time.

The initial 113-board production population completed successfully in 27m09s.
Its log showed only 14.3 seconds in parallel ATS fetching; nearly all remaining
time was row-by-row persistence of 8,625 jobs. The set-based unchanged-job path
was added from that evidence so recurring scans do not repeat thousands of
revision and location round trips.

## Hosted acceptance evidence

After the set-based path merged, the same 113-board production workflow was
rerun in a fresh idempotency window:

- GitHub Actions run: `30178625728`
- Result: succeeded
- Total workflow runtime: 1m40s
- Parallel ATS fetch/normalization: 12.2s
- Provider failures: 0
- Match refresh: completed for Adam
- Post-run Render readiness: HTTP 200, database `ok`

This is a 93.9% runtime reduction from the 27m09s first-load baseline and leaves
more than 28 minutes of headroom under the unchanged 30-minute workflow limit.

The expanded pre-merge validation normalized more than 23,000 current
postings. A complete hosted ingestion benchmark is required after deployment;
the production workflow retains its 30-minute ceiling as a performance guard.
