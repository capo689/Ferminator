# Multi-company Greenhouse tracking

## Goal

Track several companies' Greenhouse job boards simultaneously — each with
its own job history, deltas, and alerts — instead of the current
hardcoded single board (`anthropic`).

## Non-goals

- No cross-company aggregation view (e.g. "total roles across all
  companies in one chart"). The dashboard gets a per-company selector,
  not a comparison view. This can be added later if wanted, but nothing
  in this design blocks it.
- No company management UI or DB-backed company registry. The company
  list is static config (env var), not something added/removed at
  runtime without a restart.

## Approach

**One SQLite file per company.** The schema (`db.py`) does not change at
all — no `company_id` column anywhere, no composite primary keys. Each
company gets its own fully independent database file, and the existing
fetch → delta → alert → report pipeline runs unmodified against
whichever file is selected.

This was chosen over adding a `company` column to the shared schema
(which would touch nearly every query in `delta.py`, `alerts.py`,
`summarizer.py`, and `web.py`) because no cross-company aggregation was
wanted — per-company data siloing is the correct shape for a per-company
selector UI, and it's the smaller change.

Trade-off accepted: no easy way to later ask "compare 5 companies in one
query" without more work, since each company's data lives in a separate
file.

## Config (`config.py`)

- New env var `TRACKER_COMPANIES` — comma-separated Greenhouse slugs,
  e.g. `anthropic,openai,notion`. Parsed into a list: split on `,`,
  strip whitespace, lowercase, drop empties, dedupe while preserving
  order. Default: `anthropic` (preserves today's exact single-company
  behavior when unset).
- `get_db_path(db_path, company)` resolution order:
  1. `--db` flag / explicit path given → return it literally, unchanged
     from today. This is a full override regardless of company count.
  2. Otherwise, if exactly **one** company is configured → same
     filename as today (`tracker.db` locally, `/data/tracker.db` in
     Docker). Fully backward-compatible for existing deployments.
  3. If **more than one** company is configured → each company gets
     `tracker-{slug}.db` alongside where the single file would have
     been.

**Migration note:** going from one company to multiple does not
automatically rename the existing `tracker.db` to `tracker-anthropic.db`.
That's a manual one-time step (documented in the README), not something
the code does silently — a silent rename risks clobbering data if there's
a bug in the migration path; a manual `mv` makes the risk visible and
puts the user in control.

## Fetcher (`fetcher.py`)

`GREENHOUSE_API_URL`, `GREENHOUSE_DEPARTMENTS_URL`, `GREENHOUSE_OFFICES_URL`
constants become functions of a slug: `board_url(slug)`,
`departments_url(slug)`, `offices_url(slug)`. `fetch_jobs`,
`fetch_departments`, `fetch_offices`, `fetch_job_detail`,
`fetch_job_details_batch` all take a `company` parameter instead of
importing a fixed constant.

## CLI (`cli.py`)

- `cli` group gains a `--company` option alongside `--db`. It resolves:
  - `ctx.obj["companies"]` — the full configured list (from
    `TRACKER_COMPANIES`).
  - `ctx.obj["company"]` — the explicit `--company`, or the first
    configured company by default.
  - `ctx.obj["db_path"]` — resolved via `get_db_path` as above.
- Single-DB commands (`init`, `summary`, `report`, `trends`,
  `dashboard`, `alerts`) are unchanged internally — they keep using
  `ctx.obj["db_path"]`, which now resolves per-company.
  `tracker --company openai summary` works with no other changes.
- `fetch` is the one command with different default behavior: with no
  `--company` flag, it loops over every configured company, resolves
  each one's own DB path, and runs the existing fetch → delta → salary
  → alerts pipeline once per company. The current body of `fetch()` is
  extracted into `_fetch_one(company, db_path, with_salary)` so the loop
  doesn't duplicate logic. `--company openai` scopes a single run to
  one company (manual testing/debugging).
- Cron/Docker usage is unchanged: `docker compose run --rm
  tracker-fetch` still just runs `tracker fetch --with-salary`, which
  now covers every configured company in one invocation.
- `--company` is not validated against the configured list — any
  Greenhouse slug is accepted, allowing ad hoc one-off pulls
  (`tracker --company openai fetch`) without editing `TRACKER_COMPANIES`.

## Web dashboard (`web.py`, `base.html`)

- `base.html`'s `<body>` tag gets
  `hx-headers='{"X-Company": "{{ company }}"}'`. htmx headers set on an
  ancestor are inherited by every descendant request, so all periodic
  partial refreshes and the live search box automatically carry the
  current company with no per-partial template edits.
- Company tabs in the header are plain `<a href="/?company=openai">`
  links — switching companies is a normal full-page navigation, not an
  htmx swap. Only the in-page auto-refresh uses htmx.
- `/` reads `?company=` (query param, default = first configured
  company) and passes `company` and `companies` (for rendering tabs)
  into the template context.
- Every route — `/`, all `/api/*`, all `/partials/*` — gains a
  `company` param sourced from the `X-Company` header (partials/API) or
  query string (`/`), with the same default as the CLI. `_db()` becomes
  `_db(company)`, resolving the path via the same `get_db_path` the CLI
  uses.
- No changes to `dashboard.html` or any partial template — they're
  already company-agnostic, rendering whatever `conn` gives them.
- Unrecognized company slugs are not validated/rejected — same
  reasoning as the CLI. A typo'd `?company=` just resolves to an empty,
  auto-created DB file and renders the existing "no data yet" empty
  state (identical to a fresh install before the first fetch). Accepted
  minor downside: a stray empty `.db` file per typo, which is low-stakes
  and self-limiting.

## Docker Compose

No structural changes — same named volume (`anthropic-tracker-data`),
same services. Add `TRACKER_COMPANIES` to the environment block for
`web`, `tracker`, and `tracker-fetch` in `docker-compose.yml`, mirroring
how `TRACKER_DB` is already set today.

## Error handling

- **Per-company fetch failures don't block other companies.** In the
  `fetch` loop, each company's fetch is wrapped individually: on
  failure, print the error and continue to the next company. The
  command exits non-zero at the end if any company failed, but only
  after every company has been attempted.
- **ID collisions across companies:** not a concern — each company is
  fully siloed in its own SQLite file, so there's no shared ID space.

## Testing

- `test_config.py` (new): `get_db_path` resolution — single company
  preserves today's filename, multiple companies suffix by slug,
  explicit `--db` always wins regardless of company count.
- `test_fetcher.py`: extend existing mocked-`httpx` tests to confirm
  URLs are built from the passed-in slug, not a hardcoded constant.
- `test_cli.py`: `fetch` loops over all configured companies by
  default; a simulated failure for one company doesn't stop the
  others from running.
- `test_web.py` (new): `X-Company` header / `?company=` query param
  selects the correct DB file, using two temp SQLite files seeded with
  different data and asserting the response reflects the right one.
