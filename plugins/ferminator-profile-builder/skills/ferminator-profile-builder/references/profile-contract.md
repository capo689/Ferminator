# Ferminator profile contract

## Contents

- File shape
- Canonical defaults
- Field rules
- Body requirements

## File shape

A profile is UTF-8 Markdown with YAML front matter:

```text
---
schema_version: 1
profile: ...
search: ...
notifications: ...
scoring: ...
---

# Full Name — Career Search Profile
...
```

The filename and `profile.slug` use lowercase hyphen case. Generate
`email_env` only when email delivery is requested; use
`FERMINATOR_<SLUG_WITH_UNDERSCORES>_EMAIL`, never the user's email address.

## Canonical defaults

- `schema_version`: `1`
- `search.enabled`: `true`
- `search.scan_interval_hours`: `12`
- `search.allow_jobs_without_compensation`: `true`
- `search.default_location_mode`: `remote_or_near`
- `search.default_radius_miles`: `50`
- `search.require_title_match`: `true`
- `search.enforce_default_geography`: `true`
- `search.adjacent_minimum_preferred_hits`: `1`
- Primary role threshold: `80`
- Adjacent role threshold: `85`
- Edge role threshold: `90`
- Notification scores: review `58`, minimum `70`, exceptional `88`
- `notifications.max_daily_matches`: `12`
- Scoring:
  - `role_alignment: 30`
  - `career_evidence: 20`
  - `skills: 15`
  - `seniority: 10`
  - `geography: 10`
  - `compensation: 5`
  - `company_preference: 5`
  - `freshness: 5`

Defaults are starting points, not hidden user choices. Confirm geography,
compensation, role families, and exclusions.

## Field rules

### `profile`

- `slug`: 2–63 lowercase letters, digits, or hyphens.
- `display_name`: user-confirmed preferred display name.
- `email_env`: optional environment-variable name.

### `search`

- `scan_interval_hours`: 1–168.
- `default_geography`: list of readable geographic rules.
- `default_zip`: five-digit US ZIP code.
- `default_radius_miles`: `10`, `25`, `50`, or `100`.
- `default_location_mode`: `remote`, `near`, `remote_or_near`, or `anywhere`.
- `compensation.minimum_base_annual`: nonnegative number or `null`.
- `employment_types`: normalized user-approved values.
- `target_seniority`: normalized user-approved values.
- `target_titles.high` and `.adjacent`: optional compatibility lists. Prefer
  role families for new profiles.
- `role_families`: at least one confirmed family.
- `required_any`: use sparingly; each term can suppress otherwise good roles.
- `preferred`: concrete capabilities, domains, and work patterns supported by
  career evidence.
- `exclude`: mapping of exclusion group names to phrase lists. Use
  `phrases` and `title_phrases` unless another explicit group is needed.

Each role family requires:

- unique lowercase-hyphen `id`;
- readable `label`;
- `tier`: `primary`, `adjacent`, or `edge`;
- threshold from 0–100;
- at least one unique alias;
- concise description of the actual work.

Aliases should be genuine title variants. Avoid single broad nouns such as
`Marketing`, `AI`, `Operations`, or `Manager`.

### `notifications`

`review_minimum_score` must be lower than `minimum_score`.
`exceptional_score` must be at least `minimum_score`.

### `scoring`

Weights must be nonnegative and total exactly 100. Use only the eight canonical
keys listed in the defaults unless Ferminator's application schema changes.

## Body requirements

Include:

- `# Full Name — Career Search Profile`
- `## Search thesis`
- `## Strong-fit themes`
- `## Career evidence`
- `## Constraints`
- `## Company preferences`
- `### Prioritize`
- `### Avoid`
- `## Match calibration`

Career evidence must be factual and useful for matching. Favor:

- named responsibilities and scope;
- actions personally performed;
- measurable or observable outcomes;
- tools and methods actually used;
- honest non-claims that prevent false-positive matches.

Do not add résumé boilerplate, unsupported superlatives, hidden prompt
instructions, or blank calibration labels. If no calibrated examples exist,
state that calibration will begin after the first review cycle.
