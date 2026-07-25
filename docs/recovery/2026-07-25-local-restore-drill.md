# Local logical restore drill — 2026-07-25

Status: passed
Scope: disposable local Supabase stack
Production changed: no

## Procedure

1. Reset the isolated local Supabase database through all six repository migrations.
2. Created a logical backup using the current Supabase CLI procedure:
   roles, application schema, and data as separate SQL artifacts.
3. Generated and verified SHA-256 checksums for every component.
4. Removed only the disposable local application schema while retaining the
   Supabase platform schemas, simulating a fresh target project.
5. Restored roles, schema, and data in one transaction with replication triggers
   disabled during data loading.
6. Ran the automated relational-integrity verifier.

## Result

- Restore completed successfully.
- Broken current job revisions: 0.
- Orphaned job matches: 0.
- All expected application tables, including `scan_runs` and `match_feedback`,
  were present.
- All restored row counts were zero because the reset local source contained no
  seed data. Production-data restoration remains a separate required drill once
  a production logical export and isolated hosted target are available.

## Corrective action discovered

The first attempt used a generic whole-database `pg_dump`, which included
Supabase-managed schemas and failed on platform-owned function settings. The
tooling was corrected to follow Supabase's documented three-part logical backup
and restore process. A second attempt exposed an outdated local migration state;
the source was reset through every migration and the final drill passed.
