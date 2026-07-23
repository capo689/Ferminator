# Ferminator Integrated Build Plan

This plan stages shared foundations before completing feature surfaces. It
implements the ten product steps without building ten isolated systems.

## Foundation stage

1. Preserve prototype baseline and create rebuild branch.
2. Establish package boundaries, settings, logging, error model, and provider
   interfaces.
3. Add Postgres migrations, local fixtures, RLS, and repository models.
4. Add named profile schema, parser, validator, and Adam's initial profile.
5. Add company registry schema and seed format.
6. Add CI gates, secret scanning, dependency scanning, build verification, and
   test coverage threshold.

Exit: fresh environment can migrate, validate a profile, seed fixtures, and run
all checks without external credentials.

## Ingestion stage

7. Implement and contract-test Greenhouse, Lever, Ashby, SmartRecruiters,
   Workable, and BambooHR adapters.
8. Build normalized idempotent ingestion, revisions, lifecycle/reactivation,
   schema-drift reporting, retries, circuit breakers, and rate limits.
9. Add registry health and operational run views.

Exit: every V1 adapter passes fixtures and optional live smoke tests; repeated
runs create no duplicates; removed and reappearing jobs behave correctly.

## Intelligence stage

10. Implement profile compilation, eligibility, retrieval, scoring, evidence
    explanations, concerns, and evaluation fixtures.
11. Implement saved searches, freshness, repost/change detection, and company
    momentum.
12. Build daily digest selection and idempotent email delivery.

Exit: labeled evaluation set meets agreed precision/recall targets and every
score is explainable.

## Product stage

13. Build the Today briefing and opportunity cards.
14. Build Discover with natural structured query parsing, filters, saved
    searches, and comparison.
15. Build fit lens and job timeline.
16. Build Pipeline, follow-ups, notes, and campaign history.
17. Build Companies and Intelligence views.
18. Build Profile viewer, validation feedback, and safe refresh from Markdown.

Exit: target user can discover, evaluate, save, prepare, apply externally, and
track a role without instruction on desktop or mobile.

## Finish stage

19. Add Supabase auth/RLS integration for hosted environments.
20. Add Render Blueprint, GitHub scheduler, staging, preview, health checks,
    structured logs, error tracking integration points, uptime checks, backup
    and restore procedure.
21. Complete accessibility, browser, slow-network, edge-case, security, load,
    and recovery testing.
22. Complete README, API map, vendor map, runbook, privacy/retention notes,
    deployment, rollback, and handoff documentation.
23. Deploy private staging, monitor, then promote to private alpha.

Exit: FINISHER P0/P1 gates pass and the readiness report supports private alpha.

