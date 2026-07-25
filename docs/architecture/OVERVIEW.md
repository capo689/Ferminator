# Ferminator Architecture

Status: Accepted for implementation  
Date: 2026-07-23

## Product

Ferminator is a private career-intelligence system for up to five alpha users.
It monitors public company career boards, normalizes jobs across ATS platforms,
matches every job against a named Markdown career profile, and helps each person
discover, evaluate, prepare, and track applications.

The product is deliberately not a general-purpose job board. Its primary output
is a short, explainable daily briefing:

> These are the opportunities that matter today, why they match, what may not
> fit, and what to do next.

## Architectural principles

1. GitHub is the source of truth for code, migrations, profile documents, CI,
   deployment configuration, and operational documentation.
2. Render runs the FastAPI web service from the GitHub repository.
3. GitHub Actions runs a twice-daily scheduler. The scheduler reads each
   profile's own cadence and skips profiles that are not due.
4. Supabase Postgres stores normalized jobs, observations, matches, saved jobs,
   pipeline state, alerts, and operational run history.
5. Named Markdown profiles are the human-editable source of truth for search
   intent and career evidence.
6. V1 matching is deterministic and requires no AI or embedding API:
   PostgreSQL full-text retrieval, weighted phrases, exclusions, structured
   location/compensation rules, and transparent scoring.
7. Every ATS integration implements one typed adapter contract and produces the
   same normalized job record.
8. Unsupported or unstable ATS platforms cannot bypass the adapter boundary.
9. Hosted ATS application forms remain the application destination. Ferminator
   does not submit applications on a user's behalf in V1.
10. Production controls are built with the product, following FINISHER.md.

## Runtime topology

```text
Named Markdown profiles ─┐
Company registry ────────┼──── GitHub repository
Migrations/config ───────┘           │
                                     ├── Render web service
                                     │     └── FastAPI + Jinja/HTMX
                                     │
                                     └── GitHub Actions scheduler
                                           ├── Greenhouse adapter
                                           ├── Lever adapter
                                           ├── Ashby adapter
                                           ├── SmartRecruiters adapter
                                           ├── Workable adapter
                                           └── BambooHR adapter
                                                     │
                                                     ▼
                                               Supabase Postgres
                                                     │
                                      ┌──────────────┴──────────────┐
                                      ▼                             ▼
                               Daily dashboard                 Email digest
```

## Application shape

Ferminator remains a single Python application for the alpha:

- FastAPI provides HTML pages, JSON APIs, health checks, and operational routes.
- Jinja, HTMX, and small progressive-enhancement modules provide the UI.
- PostgreSQL performs durable storage and full-text retrieval.
- A CLI exposes ingestion, matching, profile validation, email digest, database
  checks, and operational commands.
- Shared service functions power both HTTP and CLI paths.

This avoids a separate frontend deployment, duplicated API models, and a second
dependency ecosystem while still supporting a highly polished interface.

## Core bounded contexts

### Profiles

Parses and validates `profiles/<person-slug>.md`. Produces:

- user identity and display preferences
- search targets and weighted concepts
- career evidence
- hard constraints and exclusions
- scoring weights
- scan cadence and notification settings

The Markdown body preserves nuanced evidence. YAML front matter contains
machine-enforced controls. Validation fails closed on malformed hard filters.

### Registry

Stores companies and public board identifiers. Entries can be enabled,
disabled, assigned a confidence level, and associated with one supported ATS.
The registry is curated in V1 and can later be augmented by discovery.

### Ingestion

Fetches public jobs through adapters with:

- explicit timeouts
- bounded retries with jitter
- bounded parallel board fetching without database connections
- serialized, transaction-safe application after the fetch phase
- response-size limits
- contract validation
- content hashing
- idempotent upserts
- structured run logs

### Matching

Uses a two-stage pipeline:

1. Eligibility removes hard mismatches such as excluded terms, unacceptable
   geography, or a disclosed salary below the configured floor.
2. Ranking scores eligible jobs across role, evidence, skills, seniority,
   location, compensation, company preference, freshness, and penalties.

Every score stores a component breakdown and matched evidence. Scores are
reproducible for a specific job revision and profile revision.

### Campaign

Tracks user-owned state independently from the public job record:

- saved/dismissed
- preparing
- applied
- interviewing
- offer
- closed
- notes, tasks, contacts, and application artifacts

### Intelligence

Derives market and company signals from job observations:

- new and removed jobs
- reposts and material edits
- company and department momentum
- skill demand
- remote-work and compensation trends

## Environment strategy

| Environment | App | Database | Profiles | Purpose |
|---|---|---|---|---|
| Local | developer machine | local Postgres or isolated Supabase branch | local files | implementation |
| Staging | Render preview/staging | Supabase development branch | non-sensitive fixtures | QA and migration testing |
| Production | Render production | dedicated Supabase project | private repository profiles | alpha use |

Production deployment is blocked until authentication, backup/restore evidence,
monitoring, and required secrets are configured.

## Authentication transition

`AUTH_MODE=off` is allowed only for local development with fixture profiles.
Hosted staging and production use Supabase magic-link authentication. Profile
records map `auth.users.id` to an allowed profile slug. RLS enforces ownership.

This keeps the first local build frictionless without creating a public,
unprotected store of résumés, notes, email addresses, and application history.

## Email

Email is a provider wrapper, not a direct vendor dependency in business logic.
The initial implementation supports a configurable SMTP transport and a console
transport for tests. A transactional email vendor can be added later without
changing digest generation.

## Deployment

A version-controlled Render Blueprint defines the web service. Scheduled
ingestion runs in GitHub Actions to keep cadence configuration in profile files
and avoid a permanently running worker during the alpha. The workflow uses
repository secrets and never commits credentials or generated user data.

## V2 boundaries

Custom career-site extraction and credentialed ATS feeds remain outside V1
because their contracts are company-specific, private, or HTML dependent. The
adapter contract and fixtures are intentionally reusable by later
implementations.
