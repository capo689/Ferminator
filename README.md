# Anthropic Hiring Tracker

Daily snapshots of Anthropic's open job listings via the Greenhouse public API. Tracks adds, removals, salary ranges, and department-level shifts. Ships with a CLI, a Rich terminal dashboard, and a web dashboard (FastAPI + htmx + Chart.js).

Built to monitor public hiring signals: which teams are growing, which roles disappeared, what compensation bands look like over time. No auth, no scraping, no PII. Pure public-API tracking.

## Quick start

```bash
git clone https://github.com/pete-builds/anthropic-tracker.git
cd anthropic-tracker
docker compose up -d web                  # dashboard on http://localhost:3710
docker compose run --rm tracker-fetch     # populate the DB (first run is empty)
./scripts/install-cron.sh                 # optional: register the daily fetch
```

That's the whole setup. No API keys. No accounts. No external services.

## API key & Greenhouse: nothing needed

Anthropic publishes its job board through Greenhouse's **public** boards API:

```
https://boards-api.greenhouse.io/v1/boards/anthropic/jobs
```

This endpoint requires no authentication, no token, no API key. It's the same data Anthropic's careers page consumes. The tracker hits it with a polite User-Agent (`anthropic-tracker/0.1.0`), retries on transport errors with exponential backoff (`config.py`), and throttles per-job detail fetches by 0.5s when collecting salary HTML.

If Anthropic ever moves off Greenhouse, this project breaks. The Greenhouse JSON shape is documented at https://developers.greenhouse.io/job-board.html.

## What it does

- **Daily fetch** of the full job list and per-job HTML, run from a host cron
- **Delta computation** against the prior snapshot (added / removed / unchanged)
- **Salary parsing** from each job's pay-transparency markup (USD, GBP, EUR; OTE vs base)
- **Alerts** on hiring freeze (>20% week-over-week drop), department surge (>50%), mass removal, new departments
- **SQLite storage** with WAL, foreign keys, and a schema-version table
- **Web dashboard** at `:3710` with auto-refreshing partials (htmx every 60s) and Chart.js trend lines

## Architecture

```
              Greenhouse API
                    │
                    ▼
            ┌───────────────┐
            │  fetcher.py   │ (httpx, retries, throttle)
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │  parser.py    │ (locations, salary regex + structured)
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │  delta.py     │ (snapshot diff, upsert, write daily row)
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │  alerts.py    │ (threshold checks, persist alerts)
            └───────┬───────┘
                    │
                    ▼
              SQLite (WAL)
              ┌───┴───┐
        ┌─────┴─┐   ┌─┴─────────┐
        │  CLI  │   │  Web (FastAPI │
        │       │   │    + htmx)    │
        └───────┘   └───────────────┘
```

Modules are independently testable: `fetcher` hits the network, `parser` is pure, `delta` takes a connection + a list of jobs, `db` owns schema.

## Running it

### Docker (recommended)

```bash
docker compose up -d web                       # start dashboard on :3710
docker compose run --rm tracker --help         # any CLI subcommand
docker compose run --rm tracker-fetch          # one-off daily fetch (preset to --with-salary)
docker compose run --rm tracker fetch          # lighter fetch, no salary parsing
docker compose run --rm tracker summary        # latest snapshot
docker compose run --rm tracker trends --days 30
docker compose run --rm tracker alerts
```

The dashboard, CLI, and cron all share the same SQLite database via the `anthropic-tracker-data` Docker volume.

### Local (development)

```bash
pip install -e ".[dev]"
tracker --help
tracker fetch --with-salary    # populates ~/.anthropic-tracker/tracker.db (or one file per TRACKER_COMPANIES)
tracker --company openai fetch # scope any command to a single company
tracker dashboard              # terminal dashboard
uvicorn anthropic_tracker.web:app --reload   # web dashboard at localhost:8000
```

### Cron (daily fetch)

The whole point of this project is *daily* snapshots — without a cron, you'll only have one data point. There's a helper:

```bash
./scripts/install-cron.sh
```

It installs this line at 06:00 ET (10:00 UTC):

```cron
0 10 * * * cd /absolute/path/to/anthropic-tracker && docker compose run --rm tracker-fetch >> $HOME/logs/anthropic-tracker.log 2>&1
```

Edit the path inside the script if you keep the repo elsewhere. Logs land in `~/logs/anthropic-tracker.log` and rotate via Docker's json-file driver (10MB × 3 in `docker-compose.yml`).

### Tests

```bash
pip install -e ".[dev]"
pytest                          # 56 tests
pytest --cov=anthropic_tracker  # coverage report
ruff check .                    # lint
```

CI runs the same on Python 3.11 / 3.12 / 3.13 plus a Trivy filesystem and image CVE scan on every push.

## Schema (12 tables)

| Table | Purpose |
|---|---|
| `jobs` | One row per job (active or historical), with first_seen / removed_date lifecycle |
| `departments`, `offices` | Reference tables, upsert on every fetch |
| `job_locations` | M:N parsed individual locations from semicolon/pipe-separated raw strings |
| `job_offices`, `job_departments` | M:N joins |
| `compensation` | Salary range per job in cents, currency, comp_type (annual/ote), raw text |
| `daily_snapshots` | One row per fetch day: total, added, removed, departments_json, locations_json, response hash |
| `weekly_metrics` | Rollup (not yet populated) |
| `alerts` | Triggered alerts with severity, message, acknowledged flag |
| `schema_version` | For future migrations |

Schema lives in `src/anthropic_tracker/db.py`. It auto-applies on first connection — no manual migration step.

## Web API

| Endpoint | Returns |
|---|---|
| `GET /` | Full HTML dashboard |
| `GET /healthz` | `{"status": "ok"}` |
| `GET /api/summary` | Latest day totals |
| `GET /api/departments` | Active roles by department |
| `GET /api/locations` | Active roles by location |
| `GET /api/trends?days=30` | Daily totals over N days |
| `GET /api/alerts` | Unacknowledged alerts |
| `GET /api/search?q=engineer` | Title search (comma-separated terms = OR) |
| `GET /api/recent-changes` | Last 10 added + last 10 removed |
| `GET /api/compensation` | Salary ranges by department |
| `GET /partials/{name}` | htmx HTML partials for the dashboard |

OpenAPI docs at `/docs` (Swagger UI) and `/redoc`.

## Configuration

Environment:

| Var | Default | Purpose |
|---|---|---|
| `TRACKER_DB` | `~/.anthropic-tracker/tracker.db` (local) / `/data/tracker.db` (Docker) | SQLite path (see `TRACKER_COMPANIES` below for how this is suffixed) |
| `TRACKER_COMPANIES` | `anthropic` | Comma-separated Greenhouse board slugs to track, e.g. `anthropic,openai,notion` |

Config constants in `src/anthropic_tracker/config.py`: timeouts, retry policy, alert thresholds.

**Tracking more than one company:** set `TRACKER_COMPANIES` to a comma-separated
list of Greenhouse board slugs. Each company gets its own database file
(`tracker-{slug}.db` next to wherever `TRACKER_DB` points), its own history, and
its own alerts. `tracker fetch` with no `--company` flag fetches every configured
company in one run; the web dashboard grows a tab per company.

**Migrating an existing single-company install:** switching from one company to
several does *not* automatically rename your existing `tracker.db`. Rename it
yourself to match the new per-company naming, e.g.:

```bash
mv ~/.anthropic-tracker/tracker.db ~/.anthropic-tracker/tracker-anthropic.db
# or, in the Docker volume:
docker compose run --rm tracker sh -c "mv /data/tracker.db /data/tracker-anthropic.db"
```

This is a manual step by design — an automatic rename risks silently clobbering
data if anything goes wrong.

## Data: backup and inspection

State lives in the Docker named volume `anthropic-tracker-data`. To back it up:

```bash
# Snapshot the DB to a tarball
docker run --rm -v anthropic-tracker-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/tracker-$(date +%F).tar.gz -C /data .

# Inspect with sqlite3 from inside the running container
docker exec anthropic-tracker-web python -c "
import sqlite3, os
c = sqlite3.connect(os.environ['TRACKER_DB'])
for row in c.execute('SELECT date, total_active_jobs, jobs_added, jobs_removed FROM daily_snapshots ORDER BY date DESC LIMIT 7'):
    print(row)
"
```

If you'd rather have the DB on the host, swap the named volume for a bind mount in `docker-compose.yml`:

```yaml
volumes:
  - ./data:/data    # instead of: tracker-data:/data
```

## Security note

The web dashboard has no auth. It exposes only public data (already on Anthropic's careers page) but should be reachable only over a trusted network (Tailscale, VPN, or behind a reverse proxy with auth). Don't expose port 3710 directly to the public internet without putting a basic-auth or OIDC layer in front of it.

## License

MIT — see [LICENSE](LICENSE).
