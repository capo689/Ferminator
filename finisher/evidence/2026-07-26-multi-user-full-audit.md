# FINISHER full-audit evidence — native Supabase multi-user beta

Date: 2026-07-26 (America/Los_Angeles)  
Scope: full audit after the native Supabase Auth production cutover  
Risk level: L2 — invited beta users, personal career data, no payments  
Production release: `1388665b7e69431917f787e9c1cc0c4e3aa87e7a`

## FINISHER package integrity

- `FINISHER-for-ChatGPT_1.zip` passed every SHA-256 entry in
  `MANIFEST.sha256`.
- The bundled scorer printed `ALL TESTS PASSED` for its 66-test suite.
- The pre-run Ferminator state validated with zero errors and zero warnings.

## Application tests

- `.venv/bin/pytest --cov=anthropic_tracker --cov=ferminator`:
  248 tests passed; total line coverage 70.13%; the configured 50% floor passed.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ferminator quality-eval`: 88.9% accuracy, zero false positives,
  one false negative.
- The latest GitHub pull-request and main-branch CI runs passed on Python
  3.11, 3.12, and 3.13, including the blocking Trivy filesystem and image
  scans.

## Live authentication and authorization

- Anonymous `GET /` redirected to `/login`.
- Adam authenticated successfully and received `200` for the user dashboard.
- Adam received `403` from `/admin`.
- SysAd authenticated successfully and received `200` from `/admin`.
- SysAd received `303` to `/admin` when requesting `/discover`.
- The administrator page exposed the unmasked ATS directory; the user-facing
  company view masks direct board URLs.
- A hostile-origin `POST /login` with `Origin: https://evil.example` received
  `403`.
- Session cookies observed during the cutover were signed, `Secure`,
  `HttpOnly`, and `SameSite=Lax`.

### P0 session replay finding

A fresh Adam session produced `200` for `/discover`. After `POST /logout`
returned `303`, replaying a copy of the pre-logout signed session cookie still
produced `200` for `/discover`.

The cause is structural: `current_user_id()` trusts the user ID in the signed
application cookie until its seven-day expiry and consults Supabase only when
refreshing an expiring token. Supabase logout removes the provider session, but
the application does not validate the access token or `session_id` on ordinary
requests. Logout therefore does not immediately invalidate a captured
Ferminator cookie.

## Live database control plane

Production Supabase project `mwqpujvtymillduxlwdg` reported:

- 16 applied production migrations, including the two native-auth control-plane
  migrations.
- 2 accounts, 1 career profile, 332,542 job matches, and 85 feedback records.
- RLS enabled on all 22 public tables.
- Ownership policies use `auth.uid()` for profile-bound data.
- Administrative tables use explicit restrictive deny policies for `anon` and
  `authenticated`.
- The security advisor reported no exposed-table error. It reported one warning:
  Supabase leaked-password protection is disabled.
- `companies` and `ats_boards` intentionally have RLS with no client policies;
  they are a server-only private registry.
- Performance advisors reported unused-index informational notices. These are
  expected on newly introduced or low-frequency beta paths and are not evidence
  of a production performance failure.

The application still connects with a privileged server database credential.
RLS protects direct Data API access, but it does not backstop a missing profile
predicate in the server repository. A true User A/User B hosted isolation
matrix has not yet been run.

## Live infrastructure

- `GET /healthz`: `200` in 83 ms.
- `GET /readyz`: `200` in 263 ms.
- `GET /login`: `200` in 74 ms.
- HTTP redirected to HTTPS with `301`.
- Runtime headers included HSTS, CSP, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, and a request ID.
- Render showed the hotfix deployment for production origin configuration live
  and attributable to commit `1388665`.
- No independent frontend/backend error tracker is installed.

## Repository and supply-chain evidence

- GitHub repository visibility is public.
- Secret scanning, push protection, and Dependabot security updates are enabled.
- The active main ruleset blocks deletion and force pushes, requires squash
  pull requests, requires resolved review threads, requires a linear history,
  and requires the Python 3.11/3.12/3.13 and security-scan checks on an
  up-to-date branch.
- The solo-beta ruleset deliberately requires zero approving reviews and has no
  bypass actors.
- GitHub Actions are version-tag pinned rather than full-commit-SHA pinned.
- `requirements.lock` is hash-pinned and production installs use
  `--require-hashes`.
- The Docker base image is digest-pinned and the image runs as an unprivileged
  user.
- Gitleaks 8.30.1 scanned all 83 commits and reported two instances of the same
  false positive: the literal non-secret board identifier
  `board_key="calibration-v2"` in `src/ferminator/calibration_v2.py`.
  No credential was present, but the scan does not yet exit cleanly because the
  false-positive fingerprint has not been allowlisted.

## Recovery evidence

- A disposable local logical backup/restore drill is documented and verified.
- A Render code rollback drill is documented.
- No verified production-data restore from Supabase into a scratch hosted
  environment exists.
- No separate hosted staging application/database exists.
- The owner and connected development agents retain standing production write
  capability.

## Deliberate beta decisions

- Maximum five user accounts, database-enforced.
- No OAuth/social login.
- No MFA yet, including for SysAd.
- Owner assigns initial passwords.
- Terms of service and privacy policy deferred until broader/public beta.
- One SysAd account.
- No payments.

These decisions may be commercially reasonable for an invited beta, but
FINISHER still records applicable P0/P1 controls as open rather than marking
them N/A.
