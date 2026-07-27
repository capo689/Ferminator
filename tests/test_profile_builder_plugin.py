from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from ferminator.profiles import load_profile

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "ferminator-profile-builder"
SKILL = PLUGIN / "skills" / "ferminator-profile-builder"
VALIDATOR_PATH = SKILL / "scripts" / "validate_profile.py"


def _validator_module():
    spec = spec_from_file_location("ferminator_profile_validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_profile_validator_accepts_real_ferminator_profile():
    validator = _validator_module()
    profile_path = ROOT / "profiles" / "adam-cagle.md"

    assert validator.validate_profile_text(profile_path.read_text(encoding="utf-8")) == []
    assert load_profile(profile_path).profile.slug == "adam-cagle"


def test_plugin_profile_validator_rejects_unfinished_template():
    validator = _validator_module()
    template = (SKILL / "assets" / "profile-template.md").read_text(encoding="utf-8")

    errors = validator.validate_profile_text(template)

    assert any("unresolved placeholder" in error for error in errors)


def test_plugin_contains_no_scaffold_placeholders():
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    manifest_text = (PLUGIN / ".codex-plugin" / "plugin.json").read_text(
        encoding="utf-8"
    )

    assert "[TODO:" not in skill_text
    assert "[TODO:" not in manifest_text


def test_plugin_validator_accepts_schema_v2_decision_profile():
    validator = _validator_module()
    raw = """---
schema_version: 2
profile:
  slug: jane-example
  display_name: Jane
search:
  enabled: true
  scan_interval_hours: 12
  schedule_preference: Morning local time
  default_geography: [Remote — United States]
  default_zip: "97702"
  home_timezone: pacific
  default_radius_miles: 50
  default_location_mode: remote_or_near
  remote_regions: [United States]
  hybrid_max_days_per_week: 0
  relocation_willing: false
  named_local_markets: []
  geography_exceptions: []
  allow_jobs_without_compensation: true
  maximum_travel_percent: 25
  compensation:
    currency: USD
    minimum_base_annual: 100000
    target_base_annual: 130000
    exceptional_opportunity_floor: 90000
    minimum_contract_hourly: 60
    bonus_equity_can_offset_base: false
  compensation_exceptions: []
  employment_types: [full-time]
  target_seniority: [senior]
  target_titles: {high: [], adjacent: []}
  role_families:
    - id: content-strategy
      label: Content Strategy
      intent: core
      tier: primary
      threshold: 50
      description: Content systems and editorial strategy.
      aliases: [Content Strategist]
      must_involve: [Editorial strategy]
      supporting_evidence: [Led a measurable editorial program]
      required_signals: [Owns content strategy]
      false_positive_patterns: [Customer support content]
      disqualifying_responsibilities: [Quota ownership]
      acceptable_seniority: [senior]
      tolerated_gaps: [New industry]
      non_claims: [No formal journalism degree]
  require_title_match: true
  enforce_default_geography: true
  adjacent_minimum_preferred_hits: 1
  required_any: []
  preferred: [editorial strategy]
  exclude: {phrases: [], title_phrases: []}
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
  company_preferences: {prefer: [], accept: [], avoid: [], never_show: []}
  work_patterns: {prefer: [], accept: [], avoid: [], never_show: []}
decision_model:
  retrieval:
    search_vocabulary: [editorial systems]
  eligibility:
    hard_rejections: [Commission-only work]
    manual_review_conditions: [Compensation missing]
  desirability:
    great_if: [Direct evidence and strong economics]
    maybe_if: [One material but survivable gap]
    wrong_if: [Central function mismatch]
  feedback:
    wrong_reason_codes: [wrong_function, qualification_gap, wrong_seniority, technical_depth, compensation, geography, travel, industry_company, work_style, not_interested, stale_listing, other]
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
# Jane Example — Career Search Profile

## Search thesis
Jane seeks senior content-strategy work that combines editorial systems, useful
technical communication, and accountable cross-functional delivery.

## Strong-fit themes
- Editorial systems and measurable content programs.

## Career evidence
- Jane personally led an editorial program, aligned stakeholders, shipped the
  operating system, and recorded measurable adoption and quality improvement.

### Explicit non-claims
- Jane does not claim a formal journalism degree.

## Role-family evidence map
- **Content Strategy:** Direct ownership supports ability and recruiter-facing
  credibility; a new industry is acceptable when the central work is unchanged.

## Constraints
- Remote United States, limited travel, and the stated compensation floors.

## Company preferences

### Prioritize
- Responsible product companies with clear customer value.

### Avoid
- Commission-only, deceptive, or primarily quota-carrying organizations.

## Decision calibration
- **Great when:** central work, evidence, economics, and interest align.
- **Maybe when:** one survivable gap prevents an immediate application.
- **Wrong when:** the central function or a hard constraint fails.
- **Calibration state:** Provisional pending real-job review.

## Unresolved evidence gaps
- Validate industry portability against the first broad calibration batch.
"""

    assert validator.validate_profile_text(raw) == []
    profile_path = ROOT / ".tmp-schema-v2-profile.md"
    try:
        profile_path.write_text(raw, encoding="utf-8")
        profile = load_profile(profile_path)
        assert profile.schema_version == 2
        assert profile.runtime_scoring["geography"] == 0
        assert profile.runtime_scoring["role_alignment"] == 30
    finally:
        profile_path.unlink(missing_ok=True)
