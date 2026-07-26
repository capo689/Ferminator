# Changelog

All material Ferminator changes are recorded here. This project follows the
Keep a Changelog structure and uses semantic versions for deployed releases.

## Unreleased

### Added

- Largest-safe-cut match gateways for geography, functional recall, hard
  disqualifiers, compensation, and refined fit.
- Per-gateway rescore accounting and an exact default-Discover production
  acceptance gate.
- JD-backed role-family discovery for unconventional titles that still contain
  meaningful career-function evidence.
- Calibration V2, a frozen 61-job human-review corpus with 11 Great, 8 Maybe,
  40 Wrong, and 2 Duplicate outcomes.
- A release gate that preserves all reviewed Great/Maybe jobs while rejecting
  at least 85% of reviewed Wrong jobs.
- Function-aware calibration signals for copy, content strategy, DevRel,
  creative technology, AI enablement, product marketing, technical roles,
  mandatory qualifications, and opportunity economics.
- A no-fetch `ferminator rescore` command and manually dispatched GitHub
  workflow for refreshing profile matches from the shared job corpus.
- A Discover control for temporarily showing hidden Wrong and Duplicate
  feedback so mistaken ratings can still be undone.
- Ferminator Profile Builder, a distributable skills-only plugin that converts
  resumes, confirmed public career sources, and a guided interview into a
  schema-validated Ferminator Markdown profile.
- Standalone profile-contract validation, evidence/provenance safeguards,
  onboarding interview guidance, and a canonical profile template.

### Changed

- Exact identity deduplication remains cheap and early; fuzzy
  application-history review is deferred until after refined matching.
- Adam's production acceptance floor now requires at least 40 genuinely visible
  jobs after role thresholds, feedback, ledger suppression, and geography.
- Adam's visibility floors now represent a controlled-review floor rather than
  requiring every candidate to clear an already-calibrated display score.
- Contract compensation now enforces a $60/hour floor independently of the
  annual full-time salary floor.
- Discover hides jobs explicitly rated Wrong or Duplicate by default.
- Production monitoring now treats Render free-tier cold starts as a bounded
  wake-up phase: up to three 20-second connection attempts with 10 seconds
  between failures (an 80-second maximum). Persistent failures still fail the
  workflow and alert.
- Monitor logs now distinguish transient transport failures from application
  health or database-readiness failures.

### Production-readiness changes required before public launch

This is a living release gate. Items stay here until completed and verified:

- [ ] Move the web service from Render's sleeping free tier to an appropriate
  paid instance before public launch.
- [ ] After that upgrade, reduce the cold-start allowance to a tighter
  production service-level objective; do not let the alpha tolerance conceal
  abnormal paid-service latency.
- [ ] Add an external alert destination and escalation owner rather than
  relying only on GitHub workflow email.
- [ ] Complete and record the hosted backup/restore and deployment rollback
  drills.
- [ ] Replace shared alpha access with production-grade per-user
  authentication and verify profile/data isolation before multi-user beta.
- [ ] Publish the required Terms of Use and Privacy Policy before accepting
  public users or collecting their career data.

## 0.8.1 - 2026-07-26

### Added

- Structured reasons and optional notes for Wrong job-match feedback.
- Markdown calibration export on the Intelligence page for profile refinement.

### Fixed

- Prevented the Wrong-feedback dialog from submitting through the triggering
  pointer event.
- Versioned browser assets so deployed JavaScript changes are not hidden by a
  stale cache.
