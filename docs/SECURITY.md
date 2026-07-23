# Security and Privacy Model

## Data classification

- Public: job listings, public company and ATS metadata
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

## Private-alpha posture

Local development may run without authentication. A hosted live-data
environment must use authenticated profile ownership before containing private
profile or campaign data. Until that gate passes, hosted preview remains
clearly labeled demo data only.

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
and never accept arbitrary user-provided hosts. Scans use one concurrency group
and a 30-minute workflow timeout.
