# Render rollback drill — 2026-07-25

Status: passed
Service: `ferminator-web`
Production URL: `https://ferminator-web.onrender.com`

## Result

1. Verified release `c6ace03` live as Ferminator `0.3.0`; `/healthz` and
   `/readyz` returned 200 and Postgres was ready.
2. Deployed the previously known-good commit `36105c0` using Render's
   specific-commit control. It became live in 38.6 seconds.
3. Verified the rolled-back application reported version `0.2.0`; health and
   database readiness both remained green.
4. Rolled forward to `c6ace03` and verified version `0.3.0`, health, and
   database readiness again.
5. Restored Auto-Deploy to **After CI Checks Pass**.

## Safety decision

Render's historical-deploy "Rollback" screen warned that it could not load the
current deploy configuration and might make unanticipated configuration
changes. The drill therefore used a specific known-good Git commit, which
exercised the same application rollback boundary while preserving the current
service configuration.

