# Changelog

All material Ferminator changes are recorded here. This project follows the
Keep a Changelog structure and uses semantic versions for deployed releases.

## Unreleased

### Added

- Source-aware effective freshness with explicit confidence and provenance:
  publication, employer update, first seen, and last checked remain distinct.
- A 60-day normal window, 61–90-day Older tier, revalidation requirement for
  older unreviewed listings, and derived 180/365-day archival policy that does
  not delete source records.
- Calibration V3 Great-versus-Maybe pairwise evaluation and a desirability
  ranking prior kept separate from eligibility and Wrong-job rejection.
- Ferminator Profile Builder schema v2: qualitative role intent, family-level
  evidence and false-positive rules, structured eligibility/desirability,
  source-aware freshness, application-history policy, expanded geography and
  economics, and canonical feedback reasons.
- Calibration V3, an 85-job frozen corpus combining both complete human-review
  batches with 13 Great, 13 Maybe, 57 Wrong, and 2 Duplicate verdicts.
- Profile-controlled home timezone and maximum travel percentage gates.
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

- Discover now preserves reviewed Great and Maybe opportunities regardless of
  age while archiving stale unreviewed intake; within each human-verdict tier,
  actionable fresh listings rank before stale reviewed leads.
- Discover date filters and Newest sorting use the explainable effective
  freshness date instead of blindly preferring the original publication date.
- The onboarding skill now asks users for core/adjacent/edge/exploratory intent
  and translates it into internal controlled-review thresholds. Email is
  opt-in, scan timing is an admin-assigned beta preference, and digest limits
  cannot cap Discover.
- Adam's title vocabulary now distinguishes editorial and technical-content
  work from PR, internal/corporate communications, generic growth marketing,
  event content, assessment content, MarTech operations, and crypto-domain
  specialist roles.
- Exact identity deduplication remains cheap and early; fuzzy
  application-history review is deferred until after refined matching.
- The production Discover audit now guards against an empty result rather than
  requiring an arbitrary 40 visible jobs. Calibration recall protects known
  good matches without pressuring the matcher to pad Discover with reviewed
  Wrong roles.
- Adam's visibility floors now represent a controlled-review floor rather than
  requiring every candidate to clear an already-calibrated display score.
- Contract compensation now enforces a $60/hour floor independently of the
  annual full-time salary floor.
- Discover hides jobs explicitly rated Wrong or Duplicate by default.
- Discover relevance ranking now treats human review as authoritative: rated
  Great jobs lead, unrated jobs follow by calibrated score, and rated Maybe
  jobs follow the unrated review queue. Wrong and Duplicate remain hidden by
  default.
- Production monitoring now treats Render free-tier cold starts as a bounded
  wake-up phase: up to three 20-second connection attempts with 10 seconds
  between failures (an 80-second maximum). Persistent failures still fail the
  workflow and alert.
- Monitor logs now distinguish transient transport failures from application
  health or database-readiness failures.
- The Render Blueprint now records the live Starter service tier so a future
  Blueprint sync cannot silently downgrade the production web service.

### Fixed

- Structured ATS pay-period variants such as `per-hour-wage` now normalize
  before compensation gating, and unlabeled hourly ranges such as
  `Hourly Pay Rate: 43.10 - 47.86 USD` are extracted correctly.
- Explicit incompatible residency timezones and travel requirements above the
  profile ceiling now fail before refined scoring.
- Generic visual Creative Director, People/HR automation, enterprise-outcomes,
  and enterprise-engagement keyword collisions no longer receive inflated
  applied-AI relevance.
- Production browser assets now use root-relative HTTPS-safe URLs behind
  Render's TLS proxy, restoring the complete dashboard interface instead of
  unstyled HTML.
- Today-page company marks now use dependable initials instead of requesting
  nonexistent per-company image files.
- JD-only role-family inference now requires the title to name a coherent
  career function, preventing AI/content vocabulary from rescuing unrelated
  legal, finance, data, engineering, and event roles.
- Overlapping ATS board records with the same normalized company and title now
  collapse after refined scoring, removing repeated Discover and digest cards
  without spending duplicate work on the full corpus.
- Profile feedback now follows identical normalized company/title listings
  across overlapping boards, preventing a rated Wrong or Duplicate job from
  reappearing through a sibling source record.
- Direct AI phrase collisions no longer rescue plainly incompatible finance,
  legal, data-architecture, research, ASIC, field-CTO, or data-governance
  titles.

### Production-readiness changes required before public launch

This is a living release gate. Items stay here until completed and verified:

- [x] Move the web service from Render's sleeping free tier to an appropriate
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
