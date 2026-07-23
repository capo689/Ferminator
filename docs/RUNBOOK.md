# Ferminator Operations Runbook

## Service checks

1. Check `GET /healthz`; confirm version, environment, and demo-mode state.
2. Check the latest GitHub `Scheduled ATS scan` run.
3. Query `ingestion_runs` for failed or long-running providers.
4. Query `ats_boards` for consecutive failures and last success.
5. Confirm the newest jobs and matches belong to the expected profile version.

## Adapter incident

1. Disable only the failing board in `config/companies.yaml`.
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

1. Select the last healthy Git commit and Docker artifact.
2. Roll Render back to that commit.
3. Do not roll database migrations backward destructively.
4. Add a forward corrective migration when schema repair is required.
5. Verify `/healthz`, one dashboard route, and one read-only database query.

## Backup and restore

Supabase production backups are the system of record. Before private alpha:

1. Confirm scheduled backups are enabled for the project plan.
2. Create a dated recovery point.
3. Restore into a non-production branch/project.
4. Verify row counts for profiles, jobs, revisions, matches, actions, and events.
5. Run a read-only dashboard smoke test against the restored database.
6. Record the recovery-point identifier, duration, and result in
   `docs/recovery/`.

Never overwrite production to test restoration.

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
