# FINISHER Baseline

Assessment date: 2026-07-23  
Stage: Architecture / pre-alpha rebuild  
Risk level: Level 1 target, currently Level 0

## Executive summary

Readiness score: **28/100**

Launch recommendation: **Do not launch**

The imported prototype demonstrates public Greenhouse ingestion, SQLite
snapshots, a CLI, and an analytics dashboard. It is not a multi-user career
product and does not yet have Postgres migrations, hosted authentication,
ownership controls, production monitoring, restore evidence, multi-ATS
adapters, email delivery, or the proposed matching and campaign workflows.

### Top five risks

1. Existing lifecycle logic fails to reactivate returning jobs and does not
   synchronize changes to active jobs.
2. The current database has no user ownership or hosted authorization model.
3. The product has no deployment separation, rollback evidence, monitoring, or
   restore test.
4. Multi-ATS ingestion contracts and rate controls do not exist.
5. The existing dashboard does not support the intended job-search workflow.

### Fastest foundational fixes

1. Preserve the prototype and rebuild on a dedicated branch.
2. Define the normalized Postgres model and migration path.
3. Define the profile schema and deterministic scoring contract.
4. Implement a common ATS adapter boundary with fixtures.
5. Establish CI, staging, structured logging, and reproducible deployment.

### Finishing sequence

Architecture → shared foundations → ingestion → matching/intelligence →
product surfaces → auth/operations → private staging → alpha.

## P0/P1/P2 risk table

| Priority | Issue | Why it matters | Evidence | Fix | Owner | Exit criteria |
|---|---|---|---|---|---|---|
| P0 | No hosted ownership enforcement | Profiles and application notes are private | SQLite schema has no users; web has no auth | Supabase auth, ownership columns, RLS tests | Engineering | User A/B tests pass |
| P0 | No tested backup/restore | Campaign history could be lost | No production DB or restore procedure | Automated backup plus staging restore drill | Engineering/Owner | Dated restore evidence |
| P0 | No safe production deployment | Bad deploy cannot be reversed confidently | No Render blueprint or staging | Git-backed staging/prod and rollback runbook | Engineering | Rollback drill passes |
| P1 | Job lifecycle defects | Matching and alerts become inaccurate | Targeted reactivation probe failed | Idempotent normalized ingestion and regression tests | Engineering | Lifecycle suite passes |
| P1 | No multi-ATS contract controls | Schema drift can silently corrupt results | Only Greenhouse fetcher exists | Typed adapters, fixtures, drift alerts, circuit breakers | Engineering | Six adapters pass |
| P1 | No observability | Failures may go unnoticed | Console output only | Structured logs, run table, error/uptime alerts | Engineering | Injected failure alerts |
| P1 | No email delivery controls | Duplicate or missing digests harm trust | Feature absent | Idempotency, retry, delivery records | Engineering | Duplicate-send test passes |
| P1 | CI lint currently fails | Main cannot be trusted as a release gate | Ruff line-length failure | Replace CI with complete gated workflow | Engineering | All required checks pass |
| P2 | No semantic reranker | Adjacent-role recall may plateau | V1 intentionally deterministic | Measure first; add optional reranker later | Product | Eval evidence supports need |
| P2 | Workday/custom sources deferred | Coverage is incomplete | Contracts are brittle | Isolated V2 adapters | Engineering | Entry criteria in ATS matrix |

## 13-layer scorecard

| Layer | Score | Status | Required next action |
|---|---:|---|---|
| Frontend foundations | 2 | Prototype only | Rebuild core flows, responsive states, accessibility |
| APIs and backend logic | 2 | Greenhouse-specific | Service boundaries, validation, error contract |
| Database and storage | 1 | Local SQLite | Postgres migrations, constraints, RLS, restore |
| Auth and permissions | 0 | None | Supabase magic link and ownership tests |
| Hosting and deployment | 1 | Docker only | Render staging/prod blueprint and rollback |
| Cloud and compute | 1 | Unmeasured | Scheduler limits, timeouts, cost forecast |
| CI/CD and version control | 2 | Basic CI | Full gates, secret/license scans, protected flow |
| Security and data protection | 1 | Public-data prototype | Threat review, headers, redaction, retention |
| Rate limiting and cost controls | 1 | Basic fetch delay | Per-provider limits, quotas, circuit breakers |
| Caching and CDN | 1 | None meaningful | Response and safe query caching |
| Load balancing and scaling | 1 | Not tested | Connection math and alpha load test |
| Error tracking and logs | 1 | Console only | Structured logs, error alerts, request/run IDs |
| Availability and recovery | 0 | None | Uptime, backups, restore, incident runbook |

## Baseline metrics

Unknown until the integrated alpha exists:

- time from job publication to discovery
- jobs fetched and normalized per run
- adapter failure rate
- match precision at top 5/top 10
- eligible-job recall on labeled samples
- digest open-to-save conversion
- saved-to-application conversion
- time from discovery to application
- support interventions per user/week
- infrastructure cost per active profile

Initial targets will be recorded before staging promotion.

## Cost surface

There are no AI token costs in V1.

| Surface | Trigger | Boundary |
|---|---|---|
| ATS HTTP requests | Scheduled scan | Per-host concurrency, retries, response caps |
| Supabase | Web and ingestion queries | Indexed queries, bounded history, connection pooling |
| Render | Web service runtime | Alpha-sized plan, health and memory monitoring |
| Email | Digest send | One idempotent digest/profile/cadence |
| GitHub Actions | Twice-daily scheduler | Due-profile skip and job timeout |

## Unknowns

- Dedicated Supabase Ferminator project and plan
- Render workspace connection and alpha service plan
- Production/staging domain choice
- SMTP or transactional email credentials
- Adam's complete evidence and compensation floor
- Initial curated company registry
- Launch date and expected alpha start date

