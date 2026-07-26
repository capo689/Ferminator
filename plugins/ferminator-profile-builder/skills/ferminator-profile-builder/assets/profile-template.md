---
schema_version: 1
profile:
  slug: first-name-last-name
  display_name: First Name
search:
  enabled: true
  scan_interval_hours: 12
  default_geography:
    - Remote — United States
  default_zip: "00000"
  default_radius_miles: 50
  default_location_mode: remote_or_near
  allow_jobs_without_compensation: true
  compensation:
    currency: USD
    minimum_base_annual: null
  employment_types:
    - full-time
  target_seniority: []
  target_titles:
    high: []
    adjacent: []
  role_families:
    - id: primary-role-family
      label: Primary Role Family
      tier: primary
      threshold: 80
      description: Replace with the work this family actually represents.
      aliases:
        - Confirmed Role Title
  require_title_match: true
  enforce_default_geography: true
  adjacent_minimum_preferred_hits: 1
  required_any: []
  preferred: []
  exclude:
    phrases: []
    title_phrases: []
notifications:
  dashboard: true
  email: true
  review_minimum_score: 58
  minimum_score: 70
  exceptional_score: 88
  max_daily_matches: 12
scoring:
  role_alignment: 30
  career_evidence: 20
  skills: 15
  seniority: 10
  geography: 10
  compensation: 5
  company_preference: 5
  freshness: 5
---

# Full Name — Career Search Profile

This file is the source of truth for Full Name's Ferminator search. It contains
only user-confirmed or source-supported professional evidence.

## Search thesis

Replace with one concrete paragraph describing the intersection of experience,
desired work, and the opportunity Ferminator should prioritize.

## Strong-fit themes

- Replace with confirmed themes.

## Career evidence

### Professional scope and outcomes

- Replace with factual evidence: situation, personal action, result, and
  demonstrated capability.

### Functional and domain expertise

- Replace with confirmed evidence.

### Tools, systems, and methods

- Replace with tools and methods used directly.

### Explicit non-claims

- Replace with qualifications Ferminator must not infer.

## Constraints

- Replace with confirmed geography, compensation, travel, schedule, and
  employment constraints.

## Company preferences

### Prioritize

- Replace with preferred company types or domains.

### Avoid

- Replace with avoided company types or domains.

## Match calibration

Calibration will begin after the user's first real-job review cycle.
