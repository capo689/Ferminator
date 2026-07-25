# ADR: GitHub, Render, and Supabase deployment topology

Date: 2026-07-23  
Status: Accepted

## Context

Ferminator needs scheduled public-data ingestion, durable private campaign
state, email, and a server-rendered dashboard. GitHub Pages alone cannot safely
persist private notes or perform scheduled server-side ingestion.

## Decision

- GitHub hosts code, profiles, migrations, CI, and scheduled ingestion.
- Render hosts the FastAPI web service from the GitHub repository.
- Supabase provides Postgres, authentication for hosted environments, RLS, and
  backups.
- GitHub Actions wakes twice daily and uses each profile's configured cadence to
  decide whether work is due.

## Alternatives considered

- GitHub Pages only: insufficient private persistence and server execution.
- Render Postgres: viable, but Supabase is already available and offers a clean
  auth/RLS transition for five users.
- Separate React frontend: more moving pieces without alpha value.

## Consequences

- Three systems require environment configuration and monitoring.
- Database migrations and RLS policies are mandatory.
- A Render Blueprint and GitHub workflow make the topology reproducible.
- Secrets are split by responsibility and never committed.

## Reversal plan

The app uses standard PostgreSQL and provider wrappers. It can move from
Supabase or Render without rewriting domain logic.

