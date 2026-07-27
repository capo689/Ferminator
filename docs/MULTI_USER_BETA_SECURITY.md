# Multi-user beta security boundary

Ferminator's private beta supports at most five career-profile users plus one
separate System Administrator account. Supabase Auth is the sole identity
provider. Render and Supabase already exist in the product, so this introduces
no paid vendor or additional identity bridge.

## Enforced controls

- Supabase owns passwords, password hashing, access tokens, refresh rotation,
  and user identifiers.
- The application accepts a friendly username but resolves the associated
  email only on the server. Failed login responses never reveal whether a
  username exists.
- Browser sessions are HttpOnly, Secure in production, SameSite=Lax, signed
  with a secret held only in Render, and refreshed before token expiry.
- State-changing production requests require the configured same-origin
  header. Login attempts are rate-limited.
- `accounts.role` is server-managed. User metadata and form values never grant
  SysAd access.
- Profile ownership remains `profiles.auth_user_id = auth.uid()`. Every
  profile-specific job match, feedback verdict, duplicate record, saved action,
  pipeline event, and notification inherits that boundary.
- Administrative accounts, schedules, run requests, and audit events have RLS
  enabled, all client grants revoked, and explicit deny policies.
- The database permits one SysAd and no more than five user accounts, including
  concurrent provisioning attempts.
- Company board URLs are removed before user templates render. The full source
  directory is available only inside the SysAd control plane.
- Account provisioning validates the complete onboarding Markdown before
  creating profile data. If database provisioning fails after Auth creation,
  the newly created Auth user is deleted as compensation.
- Initial onboarding creates a unique queued run. A partial account is never
  presented as ready.

## Deliberate beta decisions

These are accepted for the hand-selected beta, not claims of public-launch
readiness:

- No social OAuth, enterprise SSO, passkeys, or mandatory MFA yet.
- The owner sets initial passwords and communicates them out of band.
- One SysAd has full operational access to all beta accounts.
- Terms of Use and Privacy Policy remain required before public signup.
- External paging and a completed hosted restore drill remain production gates.
- The former shared password stays in Render for one rollback window. Remove
  it after the Supabase cutover and rollback verification are complete.

## Release evidence

- Every migration rebuilds successfully from an empty local Supabase database.
- The production migrations were applied before auth cutover and did not alter
  existing job, feedback, or pipeline rows.
- Ruff, the complete automated test suite, and the production Docker build pass.
- Supabase security and performance advisors are checked after every DDL
  change. Intentional private tables use explicit deny policies.
