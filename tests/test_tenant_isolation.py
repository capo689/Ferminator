"""Cross-tenant isolation tests.

These assert the boundaries the application is responsible for, and they exist
because the database does not currently enforce them for the app's own queries:
the web process connects as a role with BYPASSRLS, so the policies on
`job_matches`, `match_feedback` and `profiles` only constrain the Supabase
client path, not this one. Until that changes, application scoping *is* the
isolation, and untested isolation is unverified isolation.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import ferminator.web as web
from ferminator.web import app


def _account(role: str = "user", account_id: str = "acct-a"):
    from types import SimpleNamespace

    return SimpleNamespace(id=account_id, role=role, status="active")


def test_profile_requires_a_user_account(monkeypatch):
    """A request without a resolved account must not fall back to a profile.

    Fail-open here would hand one person's feed to whoever asked. The failure
    must be a refusal, not a default.
    """
    from types import SimpleNamespace

    monkeypatch.setattr(
        web, "get_settings", lambda: SimpleNamespace(auth_mode="supabase", demo_mode=False)
    )
    request = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(HTTPException) as excinfo:
        web._profile(request)

    assert excinfo.value.status_code == 403


def test_a_sysadmin_account_cannot_borrow_a_user_profile(monkeypatch):
    """Only `user` accounts own a profile; an admin must not inherit one."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        web, "get_settings", lambda: SimpleNamespace(auth_mode="supabase", demo_mode=False)
    )
    request = SimpleNamespace(state=SimpleNamespace(account=_account(role="sysadmin")))

    with pytest.raises(HTTPException) as excinfo:
        web._profile(request)

    assert excinfo.value.status_code == 403


def test_profile_is_loaded_for_the_requesting_account_only(monkeypatch):
    """The profile must be fetched by the caller's own account id.

    This is the load-bearing line for tenant separation on every page: if it
    ever reads a slug, a query parameter, or a default, one user sees another
    user's matches.
    """
    from types import SimpleNamespace

    asked_for: list[str] = []

    class Repo:
        def profile_for_account(self, account_id):
            asked_for.append(account_id)
            return "profile-for-" + account_id

        def close(self):
            pass

    monkeypatch.setattr(
        web, "get_settings", lambda: SimpleNamespace(auth_mode="supabase", demo_mode=False)
    )
    monkeypatch.setattr(web, "_repository", lambda: Repo())

    request = SimpleNamespace(state=SimpleNamespace(account=_account(account_id="acct-b")))
    result = web._profile(request)

    assert asked_for == ["acct-b"], "the profile must be keyed on the caller's account"
    assert result == "profile-for-acct-b"


def test_ops_is_not_public():
    """/ops publishes the private board registry.

    The registry is deliberately kept out of the public repo; an unauthenticated
    request must not be able to read it back out of the app.
    """
    with TestClient(app) as client:
        response = client.get("/ops", follow_redirects=False)

    assert response.status_code != 200 or response.json().get("status") == "demo", (
        "/ops must not serve the registry to an unauthenticated caller outside demo mode"
    )


def test_ops_requires_sysadmin_in_the_middleware():
    """Regression: /ops was reachable by any signed-in beta user.

    Authenticated is not the same as authorized. This asserts the middleware
    rule itself, since the route body has no role check of its own.
    """
    import inspect

    source = inspect.getsource(web)
    assert '("/admin", "/ops")' in source, (
        "/ops must be gated with /admin behind the sysadmin role check"
    )
