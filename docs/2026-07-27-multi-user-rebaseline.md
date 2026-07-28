# Multi-user beta plan — re-baseline audit

**Date:** 2026-07-27
**Codebase:** `main` @ `be28ed6`
**Method:** three parallel read-only code audits plus direct schema/RLS inspection and
live verification against the production service.

The beta plan was written before PR #58 shipped. This document establishes what is
actually built, so the plan can be re-sequenced against reality rather than against
the pre-#58 codebase.

---

## 1. The single highest-severity functional defect

**A user provisioned through `/admin` is never matched, and never will be.**

`cli.py:459` enumerates profiles from the git-checked-out filesystem:

```python
profiles = [load_profile(path) for path in sorted(Path("profiles").glob("*.md"))]
```

`ls profiles/` contains exactly one file: `adam-cagle.md`. Accounts created through the
admin form exist only in `public.profiles` with `source_path = 'db://profiles/<slug>/v1.md'`
(`repository.py:181`). The scanner never sees them.

Consequence: `/admin` will happily create an account that can log in, and whose
`/discover`, `/`, `/intelligence` and `/pipeline` pages render empty forever. No match is
ever scored, no digest is ever sent.

**This must be fixed before a single beta user is invited.** It is not a hardening item.

---

## 2. Status of the plan's stated gaps

The plan lists seven things as "not multi-user yet". Five are now wrong.

| Plan claim | Reality |
|---|---|
| Authentication is one shared Basic Auth password | **Wrong.** Supabase Auth shipped in #58. `shared_password` remains as dead code. |
| Every web page loads `profiles/adam-cagle.md` | **Partly wrong.** Resolved per-account under supabase mode — but see §4, it still falls back to disk. |
| Logged-in identity does not determine active profile | **Wrong.** `account_for_user` → `profile_for_account`, re-checked in SQL. |
| No admin role or admin interface | **Wrong.** `accounts.role` with CHECK, plus `GET /admin` and `POST /admin/accounts`. |
| Scan workflow is not a per-user scheduler | **Correct, and worse than stated.** See §1 and §5. |
| Directory responses include `source_url` | **Partly fixed, still leaking.** See §6. |
| RLS may be bypassed — must prove, not assume | **Correct. Proven bypassed.** See §3. |

---

## 3. RLS is inert (AUTHZ-02 is at zero, not partial)

Every user-owned table:

```
rls_enabled = true    rls_forced = FALSE    owner = postgres
```

No `FORCE ROW LEVEL SECURITY` appears in any migration, and no non-owner application
role exists. The app connects through psycopg with the server `DATABASE_URL` credential
(`repository.py:65-74`). In Postgres the table owner bypasses RLS unless force is set,
so every `auth.uid()` policy is inert on the application's connection path.

**FINISHER currently scores AUTHZ-02 as 2 (IMPLEMENTED). It should be 0 (ABSENT).**
The score credits policies that cannot execute.

The good news, established by audit: **ownership is genuinely re-checked in SQL on every
web-reachable write.** Every mutation joins `public.profiles` on the caller's slug. No
cross-tenant IDOR was found. The isolation is real — it is simply enforced in exactly one
place, with no database backstop. One future query that forgets the slug join is an
immediate breach with nothing behind it.

Options:
- **(a)** create a non-owner app role, grant narrowly, connect as it, `FORCE ROW LEVEL SECURITY`
- **(b)** accept application-level enforcement, document RLS as aspirational, and spend the
  budget on cross-tenant tests plus a repository lint asserting every statement against a
  user-owned table mentions `profile_id` or `p.slug`

(a) is correct for real résumés. It is a genuine migration with real breakage risk and
deserves its own phase, not a bullet inside Phase 2.

---

## 4. Fail-open to Adam's profile (HIGH)

`web.py:256-266`:

```python
def _profile(request: Request | None = None) -> CareerProfile:
    if request is not None and get_settings().auth_mode == "supabase":
        ...
    return load_profile(get_settings().profile_path)
```

`settings.profile_path` defaults to `profiles/adam-cagle.md`. `auth_mode` is a bare `str`
(`settings.py:18`) with no `Literal`, enum, or validator; `validate_runtime()` rejects only
the exact string `"off"` in production. Both middleware auth blocks are exact-match string
comparisons.

So `FERMINATOR_AUTH_MODE=supabse` — a typo, or the variable dropped during a Render env
edit — passes startup validation, skips both auth blocks, skips the `role != "user"` 403,
and serves every anonymous visitor Adam's profile from disk with full read **and write**
access. RLS does not backstop it (§3).

Fix: make `auth_mode` a validated enum that raises on unknown values, and invert `_profile`
to fail closed.

---

## 5. Control plane: schema is ~60% built, code is ~10%

`account_schedules` and `matching_run_queue` are **insert-only**. Rows are written at
provisioning and then read only for display. There is no worker.

| Artifact | Schema | Code |
|---|---|---|
| `account_schedules` | yes | insert + display join only; never consulted to decide when to run |
| `account_schedules.next_run_at` | yes | zero readers, zero writers |
| `matching_run_queue` | yes | insert only; no claim, no status transition, no completion |
| worker / runner | — | **does not exist** |

`render.yaml` declares one service, `type: web`. No worker, no cron. `latest_run_status`
on the admin page is permanently `queued` because nothing transitions it.

`accounts.status` allows `pending, provisioning, active, suspended, failed` but **only
`'active'` is ever written**. The lifecycle is effectively a single state. The enforcement
side works correctly (`status != 'active'` locks the user out on the next request); the
transition side does not exist.

**What is genuinely right and should be preserved:** `cli.py:486-513` already fetches each
board once and loops the shared corpus across profiles. The plan's key efficiency
requirement is architecturally satisfied — it is simply fed from the wrong profile source
(§1). Concurrency has three real layers: a Postgres advisory lock, a partial unique index
preventing overlapping runs per account, and GitHub Actions concurrency grouping. The
five-user cap and single-sysadmin constraint are enforced by DB triggers. Schedules store
IANA timezones correctly.

---

## 6. Directory masking is cosmetic

`web.py:1098-1100` nulls `source_url` under supabase auth. Three confirmed leaks remain,
all reachable by a normal `role='user'` account:

1. **`companies.html:31,38` renders `board_key` directly**, next to `provider`. The app's
   own `directory.py:65-70` builds board URLs from exactly those two fields. Nulling the
   anchor while printing the ingredients achieves nothing.
2. **`GET /ops` (`web.py:1446`) has no role gate** and returns `company`, `provider`, and
   `board_key` for every enabled board. The middleware's only role check is
   `path.startswith("/admin")`. Sysadmins are redirected away from `/ops`, so ironically
   only regular users can reach it.
3. **`apply_url` exposes the board on every job surface** (`today.html:62`,
   `discover.html:136`, `fit.html:34`, `pipeline.html:138`). Arguably required for the
   product to work, but it means `source_url` masking alone cannot achieve the objective.

Masking keys on `auth_mode`, a process-wide env var — **not on role**. The apparent
admin/user split is an accident of two templates rendering the same data differently.

---

## 7. Authentication detail

| ID | Status | Gap |
|---|---|---|
| AUTH-01 | SHIPPED | Password handling fully delegated to Supabase. Vestigial `shared_password` mode remains. |
| AUTH-03 | PARTIAL | #60 added per-request remote token validation, so revocation now works. No app-side session store. **The recorded P0 session-replay finding predates #60 and must be re-tested.** |
| AUTH-04 | SHIPPED | Hardcoded fallback secret at `web.py:222`; no `__Host-` prefix; refresh token sits in a signed-but-unencrypted cookie. |
| AUTH-05 | MISSING | No reset, no self-service change, no forced first-login rotation. The provisioning admin knows every user's password permanently. |
| AUTH-06 | PARTIAL | Per-IP only, in-process only, and the key was attacker-controlled — fixed in #68. |
| APPSEC-05 | No token | `SameSite=Lax` is the real primary defense. `_same_origin` fails open on missing `Origin` and is absent from `/logout` and `/admin/accounts`. The middleware origin gate is production-only. |

**AUTHZ-03 is clean.** Role is read only from the database, never from form, query, header,
or session. `provision_user_account` hardcodes `'user', 'active'` in SQL. An admin cannot
mint a second sysadmin through the UI, and the DB enforces it anyway.

---

## 8. Test coverage

255 tests, 40 files. For authorization: **essentially zero.**

- No User A vs User B test exists anywhere.
- `test_supabase_user_cannot_open_admin_control_plane` is the only route-level authz test,
  and it stubs a single account.
- `test_ferminator_repository.py` is entirely MagicMock-based and asserts on SQL substrings,
  never on row isolation. There is no DB fixture, so a genuine two-tenant test cannot be
  written without new infrastructure.

`TEST-01` and `APPSEC-09` are at the floor. Building the two-tenant test fixture is a
prerequisite for the dev environment, not an afterthought.

---

## 9. Revised sequence

The plan's Phase 0–9 order is sound. Changes:

**Phase 0 is largely done.** The scorecard already carries admin scope (39.0/100, 15 P0).
Correct the AUTHZ-02 score to 0 and re-test the stale AUTH-03 replay finding.

**New Phase 0.5 — fix the scanner (§1).** Provisioned users must be matched. Nothing else
in the beta matters until this works.

**Split Phase 2.** RLS enforcement (app role + FORCE + policy tests as User A/B/anon) is
its own phase with its own rollback plan.

**Add to Phase 1:** validate `auth_mode` as an enum and make `_profile` fail closed (§4).

**Phase 5 is a from-scratch build,** not an integration. The queue tables are inert.

**Phase 6 is larger than scoped:** masking must move to a role-aware response model and
cover `board_key`, `/ops`, and exports — not just `source_url`.

---

## 10. What is solid

Worth stating plainly, because the plan undersells it:

- Ownership is re-checked in SQL on every web-reachable write. No IDOR found.
- `accounts` constraints are well designed: role CHECK, the sysadmin/profile XOR, unique
  username/profile/auth_user, username regex, single-sysadmin partial index, five-user
  advisory-lock trigger.
- `matching_run_queue` has a state/timestamp consistency CHECK and a reason enum.
- Provisioning is transactional across all four inserts plus the audit event.
- Shared-corpus ingestion is already the right shape.
- Three real layers of concurrency control.

These are good foundations. They are mostly just not connected to anything yet.
