---
schema_version: 2
profile:
  slug: first-name-last-name
  display_name: First Name
search:
  enabled: true
  scan_interval_hours: 12
  schedule_preference: "Morning local time; administrator assigns beta slot"
  default_geography:
    - Remote — United States
  default_zip: "00000"
  home_timezone: pacific
  default_radius_miles: 50
  default_location_mode: remote_or_near
  remote_regions:
    - United States
  hybrid_max_days_per_week: null
  relocation_willing: null
  named_local_markets: []
  geography_exceptions: []
  allow_jobs_without_compensation: true
  maximum_travel_percent: 25
  compensation:
    currency: USD
    minimum_base_annual: null
    target_base_annual: null
    exceptional_opportunity_floor: null
    minimum_contract_hourly: null
    bonus_equity_can_offset_base: false
  compensation_exceptions: []
  employment_types:
    - full-time
  target_seniority: []
  target_titles:
    high: []
    adjacent: []
  role_families:
    - id: primary-role-family
      label: Primary Role Family
      intent: core
      tier: primary
      threshold: 50
      description: Replace with the work this family actually represents.
      aliases:
        - Confirmed Role Title
      must_involve:
        - Replace with central work.
      supporting_evidence:
        - Replace with a concise evidence reference.
      required_signals:
        - Replace with context required for ambiguous titles.
      false_positive_patterns:
        - Replace with a common wrong meaning.
      disqualifying_responsibilities:
        - Replace with work that defeats this family.
      acceptable_seniority:
        - senior
      tolerated_gaps:
        - Replace with an honest, survivable gap.
      non_claims:
        - Replace with a qualification that must not be inferred.
  require_title_match: true
  enforce_default_geography: true
  adjacent_minimum_preferred_hits: 1
  required_any: []
  preferred: []
  exclude:
    phrases: []
    title_phrases: []
  freshness:
    normal_days: 60
    older_days: 90
    revalidate_after_days: 90
    archive_unverified_after_days: 180
    default_archive_after_days: 365
    preserve_reviewed_and_pipeline: true
  duplicate_policy:
    application_suppression_days: 180
    recurrence_scope: job
    uncertain_duplicates_remain_visible: true
    application_ledger_provided: false
  company_preferences:
    prefer: []
    accept: []
    avoid: []
    never_show: []
  work_patterns:
    prefer: []
    accept: []
    avoid: []
    never_show: []
decision_model:
  retrieval:
    search_vocabulary:
      - Replace with a proven capability or work pattern.
  eligibility:
    hard_rejections:
      - Replace with an absolute rejection.
    manual_review_conditions:
      - Replace with a concern that requires judgment.
  desirability:
    great_if:
      - Replace with a Great condition.
    maybe_if:
      - Replace with a Maybe tradeoff.
    wrong_if:
      - Replace with a Wrong condition.
  feedback:
    wrong_reason_codes:
      - wrong_function
      - qualification_gap
      - wrong_seniority
      - technical_depth
      - compensation
      - geography
      - travel
      - industry_company
      - work_style
      - not_interested
      - stale_listing
      - other
    capture_great_reason: true
    capture_maybe_tradeoff: true
    capture_wrong_reason: true
notifications:
  dashboard: true
  email: false
  review_minimum_score: 58
  minimum_score: 70
  exceptional_score: 88
  max_daily_matches: 12
scoring:
  functional_fit: 30
  career_evidence: 20
  ats_credibility: 15
  skills: 10
  seniority: 10
  opportunity_economics: 10
  company_preference: 5
---

# Full Name — Career Search Profile

## Search thesis

Replace with the intersection of demonstrated experience, desired work, and
the opportunities Ferminator should prioritize.

## Strong-fit themes

- Replace with confirmed themes.

## Career evidence

- Replace with factual situation, personal action, observable result, and
  demonstrated capability.

### Explicit non-claims

- Replace with qualifications Ferminator must not infer.

## Role-family evidence map

- **Primary Role Family:** Replace with the evidence that supports the family,
  the evidence likely to survive ATS review, and any material gap.

## Constraints

- Replace with geography, economics, travel, schedule, and employment rules.

## Company preferences

### Prioritize

- Replace with preferred industries, stages, sizes, or work environments.

### Avoid

- Replace with avoid and never-show company patterns.

## Decision calibration

- **Great when:** Replace with confirmed Great logic.
- **Maybe when:** Replace with the tradeoff that prevents Great.
- **Wrong when:** Replace with hard or preference-based rejection logic.
- **Calibration state:** Provisional until the first real-job review cycle.

## Unresolved evidence gaps

- Replace with an honest unresolved question or state that none remain.
