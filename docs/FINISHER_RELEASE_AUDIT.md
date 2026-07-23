# FINISHER Release Audit

Assessment date: 2026-07-23  
Release candidate: `codex/dream-product`  
Risk level: Level 1 private-alpha target

## Decision

Engineering readiness: **88/100**

Local release candidate: **PASS**  
Hosted private-alpha launch: **BLOCKED ON OWNER CONFIGURATION**

The application, database migration, six ATS adapter families, deterministic
matching, dashboard, persisted pipeline, digest, scheduled workflow, container,
security baseline, and operational documentation are implemented. It is not
honest to call the hosted system finished until the dedicated Supabase project,
Render account selection, SMTP secrets, and Adam's missing profile evidence are
supplied and verified in their hosted environments.

## Verified evidence

- 119 automated tests pass on Python 3.12; CI also targets 3.11 and 3.13.
- Ruff passes with no findings.
- Combined test coverage is 68%; the enforced floor is 50%.
- The initial Postgres migration rebuilds successfully from an empty database.
- 2,183 jobs were imported from 14 enabled public boards across Greenhouse,
  Ashby, SmartRecruiters, Workable, and BambooHR.
- Lever's adapter passed its live smoke test; its demonstration board remains
  disabled in the production registry.
- A second complete scan produced zero duplicate additions and zero spurious
  updates on every board.
- Matching completed for the named Adam profile without timezone errors.
- Live dashboard routes read Postgres data; Save, Prepare, and Dismiss persist
  pipeline state and append an action event.
- Digest selection enforces the profile's minimum score and notification
  idempotency.
- The production image builds from the hash-locked dependency file, runs as the
  `ferminator` user, reports healthy, rejects unauthenticated dashboard access,
  and returns the expected security headers.
- Desktop and 390-pixel mobile layouts were exercised without horizontal
  overflow; the mobile menu and Fit Lens fixes were verified.

## P0 / P1 disposition

| Priority | Control | Status | Evidence / remaining work |
|---|---|---|---|
| P0 | Private access | Implemented | Constant-time shared-password gate; production refuses auth-off and demo mode |
| P0 | Ownership controls | Implemented, hosted test pending | Ownership-aware schema, RLS policies, static tests; needs dedicated hosted project |
| P0 | Backup and restore | Procedure ready, drill pending | Runbook exists; hosted recovery point cannot exist before project provisioning |
| P0 | Safe deployment | Blueprint ready, hosted test pending | Docker and health gates pass; Render login/account selection is outstanding |
| P1 | Job lifecycle | Passed | Removal, mass-removal, reactivation, revisions, and two-pass live idempotency |
| P1 | Multi-ATS controls | Passed | Six typed adapter families, bounded retries/timeouts/response size, live smoke tests |
| P1 | Observability | Implemented | JSON request logs, request IDs, ingestion run history, board health fields |
| P1 | Email controls | Implemented, delivery pending | Idempotent claim/send records and preview pass; SMTP credentials absent |
| P1 | CI/security | Implemented | Multi-Python test matrix, coverage, Docker, Trivy filesystem/image gates |

## Thirteen-layer scorecard

| Layer | Score | Status |
|---|---:|---|
| Frontend foundations | 8 | Responsive product UI, accessible navigation, empty/error-safe primary flows |
| APIs and backend logic | 9 | Typed boundaries, validation, deterministic matching, persisted actions |
| Database and storage | 9 | Normalized Postgres, constraints, indexes, migration reset proven |
| Auth and permissions | 7 | Alpha gate and RLS exist; hosted multi-profile isolation drill pending |
| Hosting and deployment | 7 | Reproducible image and Render blueprint; hosted rollout pending |
| Cloud and compute | 8 | Bounded connections, job timeout, cadence, no AI-token cost |
| CI/CD and version control | 9 | Gated CI, pinned runtime, SBOM/provenance request, Trivy |
| Security and data protection | 8 | Non-root image, headers, no committed secrets, private-data runbook |
| Rate limiting and cost controls | 8 | Curated boards, host-safe requests, retry and payload caps |
| Caching and CDN | 5 | Not required for five-user alpha; no shared response cache |
| Load balancing and scaling | 7 | Five-user boundary and bounded pool; hosted load evidence pending |
| Error tracking and logs | 8 | Structured logs and run state; external alert destination pending |
| Availability and recovery | 6 | Health check/runbook complete; hosted backup/restore drill pending |

## Required owner inputs before hosted launch

1. Confirm the Supabase organization and approve the quoted project cost.
2. Choose the Render login account and complete the browser authorization.
3. Supply the private-alpha password and SMTP sender credentials in provider
   secret stores.
4. Replace every `TODO:` evidence line in `profiles/adam-cagle.md` with verified
   career facts. Current behavior correctly returns no digest candidates above
   the configured 70-point threshold.
5. After provisioning, execute and record the hosted RLS isolation test,
   backup/restore drill, scheduled scan, real email delivery, and rollback drill.

Workday, iCIMS, JazzHR, Recruitee, Personio, Teamtailor, Rippling, and bespoke
career sites remain explicitly deferred to V2 because they do not offer the
same reliable public structured interface as the V1 adapter set.
