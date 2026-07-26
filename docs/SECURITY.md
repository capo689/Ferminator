# Security and Privacy Model

## Data classification

- Public: individual job listings and their originating public application URLs
- Proprietary: the aggregated, validated company directory, ATS board identifiers,
  source health, and validation evidence
- Private: career profiles, target constraints, scores, saved jobs, notes,
  application state, contacts, and email destinations
- Secret: database credentials, SMTP credentials, deploy credentials

No resumes or correspondence attachments are stored in V1.

## Trust boundaries

ATS responses are untrusted third-party input. Adapters enforce HTTPS, timeouts,
bounded retries, response-size limits, typed normalization, HTML sanitization,
and lifecycle safety checks. Listing text never becomes an instruction.

The server-side database credential is never exposed to browser code.
Production mode refuses to start with demo mode or authentication disabled.
Postgres RLS is enabled for every application table; ingestion writes remain
service-role only.

The complete company and ATS registry exists only in protected Supabase tables.
The `anon` and `authenticated` Data API roles have no privileges on those
tables. Logged-in application users may browse the directory through the
server-rendered `/companies` page, but the repository, static assets, and
unauthenticated endpoints contain no bulk registry artifact.

## Private-alpha posture

Local development may run without authentication. Hosted live-data environments
must refuse to start with authentication disabled. The current private alpha
uses rate-limited shared-password authentication.

## Retention

- Active and historical public job revisions: retained for trend analysis
- Ingestion telemetry: 90 days, then aggregate or delete
- Failed notification metadata: 90 days
- Profile and campaign data: retained while the alpha participant is active
- Account deletion: delete the profile; cascading foreign keys remove matches,
  actions, events, searches, and notifications

Backups expire according to the configured Supabase retention window.

## Abuse and cost controls

V1 has no generative-AI API and therefore no token-cost or prompt-injection
surface. ATS requests are curated, rate-limited, retried only within bounds,
and never accept arbitrary user-provided hosts. Scans use one concurrency group,
two deterministic registry shards, and a 45-minute workflow timeout.
