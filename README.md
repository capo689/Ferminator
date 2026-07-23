# Ferminator

Ferminator is a private, profile-driven career intelligence system. It searches
public structured job boards, normalizes every role into one model, ranks roles
against a named Markdown career profile, and presents the results in a focused
dashboard and email digest.

No AI API key is required. Matching is deterministic, explainable, and built
from profile rules, full-text retrieval, title/location/compensation gates, and
weighted evidence.

## V1 scope

- ATS adapters: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, BambooHR
- Curated company registry; demo boards are disabled
- Named Markdown profiles for up to five private-alpha users
- Remote-US defaults that each profile can override
- Job revisions, removals, reactivations, and ingestion safety limits
- Today, Discover, Pipeline, Companies, Intelligence, and Profile views
- Supabase Postgres schema with RLS
- Render web deployment and GitHub Actions scanning

Workday and brittle/custom career-site extraction are intentionally deferred to
V2. See [ATS_MATRIX.md](docs/architecture/ATS_MATRIX.md).

## Local development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/ferminator profile validate
.venv/bin/ferminator registry-validate
.venv/bin/uvicorn ferminator.web:app --reload
```

The UI starts in clearly labeled demo mode. Live ingestion requires
`DATABASE_URL` for a dedicated Ferminator Supabase project:

```bash
DATABASE_URL=... .venv/bin/ferminator scan
```

Never commit credentials. Copy `.env.example` into your deployment provider and
store values in its secret manager.

## Profiles

Profiles live in `profiles/<person-name>.md`. YAML front matter controls search,
location, compensation, cadence, notifications, and scoring. The Markdown body
contains career evidence used by matching. Validate every edit:

```bash
ferminator profile validate profiles/adam-cagle.md
```

## Verification

```bash
ruff check .
pytest --cov=anthropic_tracker --cov=ferminator --cov-report=term-missing
docker build -t ferminator:local .
```

Architecture, data model, decisions, build stages, and FINISHER readiness are in
`docs/`. The legacy tracker remains temporarily available as `tracker` while
Ferminator reaches data-parity and the migration is proven.

The current evidence-based release decision is recorded in
[FINISHER_RELEASE_AUDIT.md](docs/FINISHER_RELEASE_AUDIT.md). It distinguishes
completed engineering from the hosted checks that require owner account and
credential choices.
