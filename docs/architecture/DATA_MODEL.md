# Ferminator Data Model

## Ownership

All user-created records are owned by `profile_id`. Public source data is
shared. RLS protects both direct user tables and joins that could reveal user
activity.

## Core tables

### `profiles`

- `id uuid primary key`
- `auth_user_id uuid unique`
- `slug text unique`
- `display_name text`
- `email text`
- `source_path text`
- `source_hash text`
- `profile_version integer`
- `scan_interval_hours integer`
- `scan_enabled boolean`
- timestamps

### `companies`

- `id uuid primary key`
- `slug text unique`
- `name text`
- `website_url text`
- `career_url text`
- `enabled boolean`
- metadata and timestamps

### `ats_boards`

- `id uuid primary key`
- `company_id uuid`
- `provider enum`
- `board_key text`
- `region text`
- `source_url text`
- `enabled boolean`
- validation status, failure counters, and timestamps
- unique `(provider, board_key, region)`

### `jobs`

Canonical current public job identity:

- `id uuid primary key`
- `ats_board_id uuid`
- `source_job_id text`
- `source_key text unique`
- normalized title, description, department, team, employment and workplace type
- compensation fields
- job/apply URLs
- `first_seen_at`, `last_seen_at`, `published_at`, `updated_at`
- `active boolean`
- `removed_at`
- `current_revision_id uuid`

### `job_revisions`

Immutable meaningful versions:

- `id uuid primary key`
- `job_id uuid`
- `content_hash text`
- normalized searchable document
- raw normalized JSON
- `observed_at`
- unique `(job_id, content_hash)`

### `job_locations`

- `job_id uuid`
- normalized location fields
- `is_primary boolean`
- unique normalized location per job

### `ingestion_runs`

- provider/board/run identifiers
- status and timing
- fetched, inserted, updated, removed, and failed counts
- safe error code/message
- request and retry metrics

### `job_matches`

- `profile_id uuid`
- `job_id uuid`
- profile and job revision versions
- total score
- eligibility state
- component score JSON
- matched evidence JSON
- concerns JSON
- timestamps
- unique `(profile_id, job_id, profile_version, job_revision_id)`

### `job_actions`

Current user-owned pipeline state:

- `profile_id uuid`
- `job_id uuid`
- `state enum`
- priority
- notes
- follow-up date
- timestamps
- unique `(profile_id, job_id)`

### `action_events`

Immutable campaign timeline for state changes and notes.

### `saved_searches`

Named search expressions and presentation preferences per profile.

### `notifications`

Idempotent digest/alert delivery records with provider status and retry count.

## Search indexes

- GIN full-text index on the job revision search vector
- trigram index on normalized job title and company name
- partial indexes for active jobs, undelivered notifications, due follow-ups,
  and enabled boards
- B-tree indexes on ownership and foreign-key columns

## Retention

- Raw HTTP bodies are not stored.
- Normalized job revisions are retained for hiring-history intelligence.
- Operational error details are redacted and retained for 30 days initially.
- Deleted profiles cascade user-owned matches, actions, searches, and
  notifications.
- Shared public job data remains unless no profile references it and retention
  cleanup removes it.

