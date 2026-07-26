# Ferminator

Ferminator is a private, profile-driven career intelligence system. It searches
public structured job boards, normalizes every role into one model, ranks roles
against a named Markdown career profile, and presents the results in a focused
dashboard and email digest.

No AI API key is required. Matching is deterministic, explainable, and built
from profile rules, full-text retrieval, title/location/compensation gates, and
weighted evidence.

## V1 scope

- ATS adapters: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, BambooHR,
  Workday, Breezy, and Rippling
- Curated company registry; demo boards are disabled
- Searchable live ATS directory with source-health tracking
- Bounded parallel bulk ingestion for large registries
- Named Markdown profiles for up to five private-alpha users
- Remote-US defaults that each profile can override
- Job revisions, removals, reactivations, and ingestion safety limits
- Today, Discover, Pipeline, Companies, Intelligence, and Profile views
- Supabase Postgres schema with RLS
- Render web deployment and GitHub Actions scanning

Credentialed feeds such as Jobvite and brittle/custom career-site extraction
remain outside the no-key release. See
[ATS_MATRIX.md](docs/architecture/ATS_MATRIX.md).

## Local development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/ferminator profile validate
DATABASE_URL=postgresql://... .venv/bin/ferminator registry-validate
.venv/bin/uvicorn ferminator.web:app --reload
```

Validate a saved HTML source list or `company,ats,board_url` CSV before adding
its boards:

```bash
ferminator directory-check /private/master-list.html --workers 8 \
  --json-output /private/board-validation-YYYY-MM-DD.json
```

Merge only the successful results into the registry:

```bash
ferminator directory-merge /private/board-validation.json \
  --registry /private/current-registry.yaml \
  --output /private/updated-registry.yaml
DATABASE_URL=postgresql://... \
  ferminator registry-import /private/updated-registry.yaml
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

Material product changes and the living public-production release gate are
maintained in [CHANGELOG.md](CHANGELOG.md). A change is not production-ready
merely because it is deployed to the private alpha; every unchecked item in
that gate must be explicitly resolved or accepted before public launch.

## Acknowledgments

Special thanks to **Fermin Romero III** for the idea that inspired Ferminator.
