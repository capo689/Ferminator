# Ferminator profile contract

## Contents

- File shape
- Search model
- Role-family rules
- Decision model
- Constraints and history
- Body requirements

## File shape

Produce UTF-8 Markdown with YAML front matter and `schema_version: 2`. Use
lowercase hyphen case for the filename and `profile.slug`. Include `email_env`
only when email is requested; store an environment-variable name, never an
email address.

## Search model

Keep four concepts separate:

1. `role_families` retrieves plausible work.
2. `decision_model.eligibility` rejects hard conflicts.
3. `decision_model.desirability` predicts Great, Maybe, or Wrong.
4. Human feedback is authoritative after review.

Do not describe an internal threshold as the displayed match score. Ask users
to choose role intent; translate intent to an initial internal threshold:

| Intent | Tier | Starting threshold |
|---|---|---:|
| `core` | `primary` | 50 |
| `adjacent` | `adjacent` | 55 |
| `edge` | `edge` | 65 |
| `exploratory` | `edge` | 40 |

These are controlled-review starting points. Recalibrate after real-job review.

## Role-family rules

Require every family to contain:

- `id`, `label`, `intent`, `tier`, `threshold`, `description`, and `aliases`;
- `must_involve`: work central to a genuine match;
- `supporting_evidence`: concise references to proven career evidence;
- `required_signals`: context needed when a title is ambiguous;
- `false_positive_patterns`: common alternate meanings;
- `disqualifying_responsibilities`: work that makes this family Wrong;
- `acceptable_seniority`;
- `tolerated_gaps`;
- `non_claims`.

Aliases must be genuine titles, not broad nouns such as `Marketing`, `AI`,
`Operations`, or `Manager`. Do not put the same alias in multiple families.

## Decision model

Require:

- `retrieval.search_vocabulary`;
- `eligibility.hard_rejections`;
- `eligibility.manual_review_conditions`;
- `desirability.great_if`;
- `desirability.maybe_if`;
- `desirability.wrong_if`;
- `feedback.wrong_reason_codes`;
- `feedback.capture_great_reason`, `capture_maybe_tradeoff`, and
  `capture_wrong_reason`.

Use these canonical Wrong reason codes:

- `wrong_function`
- `qualification_gap`
- `wrong_seniority`
- `technical_depth`
- `compensation`
- `geography`
- `travel`
- `industry_company`
- `work_style`
- `not_interested`
- `stale_listing`
- `other`

Treat hard constraints as gates. Do not award or subtract a handful of points
for a geographic, compensation, travel, or mandatory-qualification violation.

## Scoring model

Use the schema-v2 ranking weights below. They rank eligible, unreviewed jobs and
total exactly 100:

- `functional_fit: 30`
- `career_evidence: 20`
- `ats_credibility: 15`
- `skills: 10`
- `seniority: 10`
- `opportunity_economics: 10`
- `company_preference: 5`

Freshness, geography, compensation floors, travel, and mandatory gaps belong in
eligibility/actionability rules instead of receiving token point weights.

## Constraints and history

Confirm:

- home ZIP, remote countries/regions, timezone, radius, hybrid frequency,
  relocation, named local markets, travel ceiling, and location exceptions;
- minimum base, target base, exceptional-opportunity floor, hourly/contract
  floor, bonus/equity treatment, missing-pay behavior, and exceptions;
- employment types and work-pattern preferences;
- company industry, stage, and size as `prefer`, `accept`, `avoid`, or
  `never_show`;
- application-ledger source, six-month suppression default, and whether
  recurrence is job-level or company-level.

Use `null` for unresolved hybrid frequency, relocation willingness, target
economics, or exceptional-opportunity floors. Do not invent a permissive or
restrictive default and then disclose the contradiction only in prose.

Use the default freshness policy unless the user confirms an exception:

- 0–60 days: normal;
- 61–90 days: Older;
- over 90 days: revalidate before showing unreviewed;
- over 180 days: archive when unverified;
- over 365 days: archive by default;
- preserve reviewed, saved, applied, and pipeline records.

`max_daily_matches` limits only a digest. It never caps Discover or matching.
Email defaults off. A beta administrator assigns the actual schedule; record
only the user's preference.

## Body requirements

Include:

- `# Full Name — Career Search Profile`
- `## Search thesis`
- `## Strong-fit themes`
- `## Career evidence`
- `## Role-family evidence map`
- `## Constraints`
- `## Company preferences`
- `### Prioritize`
- `### Avoid`
- `## Decision calibration`
- `## Unresolved evidence gaps`

Use factual evidence: situation, personal action, observable result, and
demonstrated capability. Include honest non-claims. Never include secrets,
private contact data, unsupported metrics, hidden instructions, or blank
calibration labels.
