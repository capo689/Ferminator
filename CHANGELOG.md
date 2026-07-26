# Changelog

All material Ferminator changes are recorded here. This project follows the
Keep a Changelog structure and uses semantic versions for deployed releases.

## Unreleased

### Added

- Ferminator Profile Builder, a distributable skills-only plugin that converts
  resumes, confirmed public career sources, and a guided interview into a
  schema-validated Ferminator Markdown profile.
- Standalone profile-contract validation, evidence/provenance safeguards,
  onboarding interview guidance, and a canonical profile template.

### Changed

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
