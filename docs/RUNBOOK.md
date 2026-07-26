# Ferminator Operations Runbook

## Service checks

1. Check `GET /healthz`; confirm version, environment, and demo-mode state.
2. Check authenticated `GET /ops`; confirm the latest full scan completed and no
   board is unexpectedly degraded.
3. Check the latest GitHub `Scheduled ATS scan` and `Production health monitor`.
4. Query `ingestion_runs` for failed or long-running providers.
5. Query `ats_boards` for consecutive failures and last success.
6. Confirm the newest jobs and matches belong to the expected profile version.

An HTTP 200 containing an empty provider payload is not automatically healthy.
Mass-removal protection, duplicate-ID validation, and per-board run records must
all agree before treating zero jobs as a real source state.

## Adapter incident

1. Disable only the failing board in the protected Supabase registry.
2. Preserve the response shape and error code without secrets or personal data.
3. Run fixture tests and a bounded `ferminator ats-smoke`.
4. Re-enable after two successful validations.
5. Never compensate by scraping authenticated candidate or internal APIs.

Mass-removal protection deliberately fails a board when an implausible share of
active jobs disappears. Investigate before increasing the threshold.

## Digest incident

Notifications are claimed by a unique daily idempotency key before SMTP send.
Check `notifications.status`, `attempt_count`, and `last_error_code`. Do not
manually delete a sent row to force delivery; generate an explicitly named
one-off message if a resend is genuinely required.

## Rollback

1. Record the current deploy ID and the last known-good deploy ID.
2. In Render, select the last known-good deploy and choose **Rollback**.
3. Do not roll database migrations backward destructively. The application must
   remain compatible with additive migrations from the failed release.
4. Run `python scripts/smoke_deployment.py https://ferminator-web.onrender.com
   --password "$FERMINATOR_ALPHA_PASSWORD"`.
5. Confirm `/healthz`, `/readyz`, `/`, and `/ops`; then inspect new error logs.
6. Record duration, deploy IDs, result, and any corrective action in
   `docs/recovery/`.
7. Repair forward on a new commit and repeat the smoke test after redeployment.

## Backup and restore

Free-tier Supabase projects do not receive automatic daily backups. Ferminator's
logical export is therefore the recovery system of record:

1. Install Docker and the Supabase CLI.
2. Run `DATABASE_URL="$DATABASE_URL" scripts/backup_database.sh backups`.
3. Copy the dated directory to encrypted off-site storage; repository and CI
   artifacts are not approved backup locations.
4. Create a new isolated Supabase project or local Supabase environment.
5. Run `RESTORE_DATABASE_URL="$RESTORE_DATABASE_URL"
   scripts/restore_database.sh backups/ferminator-TIMESTAMP`.
6. Verify row counts, current revisions, and match ownership using the automatic
   verifier.
7. Run a read-only dashboard smoke test against the restored database.
8. Record the recovery point, checksum, duration, and result in
   `docs/recovery/`.

Never overwrite production to test restoration.

The restore script refuses the source URL when it is supplied as `DATABASE_URL`,
requires checksum verification, and refuses a target that already contains
Ferminator tables.

## Secret rotation

Rotate the database credential, SMTP credential, and any hosting deploy token
independently. Update provider secrets, redeploy, run health and digest-preview
checks, then revoke the old credential. Never place secret values in issues,
logs, screenshots, or this repository.

## Incident severity

- SEV-1: private profile/action data exposed, destructive data loss, credential leak
- SEV-2: all ingestion or dashboard access unavailable
- SEV-3: one adapter, digest, or non-critical view degraded

For SEV-1, disable public access and scheduled writes first, preserve evidence,
rotate credentials, and notify affected alpha users.
