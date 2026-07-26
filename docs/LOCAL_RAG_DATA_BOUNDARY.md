# Ferminator Local RAG and Live Data Boundary

Ferminator separates stable, reviewable knowledge from live transactional data.
This keeps Supabase compact without making the deployed application depend on
Render's temporary filesystem.

## Versioned local knowledge

These sources belong in GitHub and are loaded as a small retrieval corpus:

- the company and ATS board registry: protected Supabase tables, never local RAG;
- `profiles/*.md`: one user-confirmed career evidence profile per person;
- profile role families, aliases, exclusions, thresholds, and search cadence;
- `calibration/`: reviewed job examples and scoring labels;
- documented scoring policies and ATS adapter rules.

Changes to these files are deliberate, reviewable, recoverable, and deployed
with the application. They should not be copied into per-request database rows
unless a compiled snapshot is required to reproduce a score.

## Shared live-market cache

Supabase stores one shared current record for each job:

- normalized job facts and source identity;
- one canonical plain-text job description;
- current locations and compensation;
- revision identity and lifecycle timestamps.

All profiles reuse this market cache. Ferminator must not store another full JD
for each user. HTML, concatenated search text, and embedded description copies
are not canonical storage.

## Per-user transactional facts

Supabase remains the system of record for:

- match scores tied to profile and job revisions;
- match feedback;
- pipeline state, notes, priority, and follow-up dates;
- application history and duplicate suppression;
- notification delivery state.

These records require consistency across browsers and users and therefore must
not live only in GitHub or on Render's ephemeral disk.

## Optional offline archive

Retired job revisions may later be exported as compressed JSONL for offline
market research. Such an archive is not part of the live request path, must have
documented retention, and must not include user notes or credentials.

## Retrieval rule

Use the smallest authoritative source:

1. Retrieve stable career and directory knowledge from local versioned files.
2. Retrieve current shared job facts from Supabase.
3. Retrieve private workflow facts only for the active profile.
4. Never duplicate a complete JD merely to make it easier to query.
