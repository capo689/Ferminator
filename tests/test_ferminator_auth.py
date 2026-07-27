from time import time

import pytest
import respx
from httpx import Response

from ferminator.auth import (
    AuthenticationError,
    SupabaseAuthClient,
    current_user_id,
)
from ferminator.settings import Settings


def auth_settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
        supabase_secret_key="sb_secret_test",
    )


@pytest.mark.anyio
@respx.mock
async def test_sign_in_returns_normalized_session_tokens() -> None:
    respx.post("https://example.supabase.co/auth/v1/token?grant_type=password").mock(
        return_value=Response(
            200,
            json={
                "access_token": "header.payload.signature",
                "refresh_token": "refresh",
                "expires_at": int(time()) + 3600,
                "user": {"id": "user-id", "email": "person@example.com"},
            },
        )
    )
    tokens = await SupabaseAuthClient(auth_settings()).sign_in(
        "person@example.com",
        "correct horse battery staple",
    )
    assert tokens.user_id == "user-id"
    assert tokens.email == "person@example.com"


@pytest.mark.anyio
@respx.mock
async def test_sign_in_uses_generic_error_for_bad_credentials() -> None:
    respx.post("https://example.supabase.co/auth/v1/token?grant_type=password").mock(
        return_value=Response(400, json={"message": "Invalid login credentials"})
    )
    with pytest.raises(AuthenticationError, match="not recognized"):
        await SupabaseAuthClient(auth_settings()).sign_in("person@example.com", "wrong")


@pytest.mark.anyio
@respx.mock
async def test_admin_user_creation_keeps_privileged_key_server_side() -> None:
    route = respx.post("https://example.supabase.co/auth/v1/admin/users").mock(
        return_value=Response(201, json={"id": "new-user-id"})
    )
    user_id = await SupabaseAuthClient(auth_settings()).create_user(
        email="person@example.com",
        password="a very long password",
        username="person",
    )
    assert user_id == "new-user-id"
    assert route.calls[0].request.headers["authorization"] == "Bearer sb_secret_test"


@pytest.mark.anyio
@respx.mock
async def test_authenticated_user_id_validates_access_token_with_supabase() -> None:
    route = respx.get("https://example.supabase.co/auth/v1/user").mock(
        return_value=Response(200, json={"id": "user-id"})
    )
    user_id = await SupabaseAuthClient(auth_settings()).authenticated_user_id("access")
    assert user_id == "user-id"
    assert route.calls[0].request.headers["authorization"] == "Bearer access"


@pytest.mark.anyio
@respx.mock
async def test_authenticated_user_id_rejects_revoked_token() -> None:
    respx.get("https://example.supabase.co/auth/v1/user").mock(
        return_value=Response(401, json={"message": "session revoked"})
    )
    with pytest.raises(AuthenticationError, match="session expired"):
        await SupabaseAuthClient(auth_settings()).authenticated_user_id("revoked")


@pytest.mark.anyio
async def test_current_user_rejects_cookie_when_provider_session_is_invalid() -> None:
    class SessionRequest:
        session = {
            "access_token": "revoked",
            "refresh_token": "refresh",
            "expires_at": int(time()) + 3600,
            "user_id": "user-id",
            "email": "person@example.com",
        }

    class RevokedClient:
        async def authenticated_user_id(self, _access_token):
            raise AuthenticationError("Your session expired. Please sign in again.")

    request = SessionRequest()
    assert await current_user_id(request, RevokedClient()) is None
    assert request.session == {}


@pytest.mark.anyio
async def test_current_user_rejects_identity_mismatch() -> None:
    class SessionRequest:
        session = {
            "access_token": "valid",
            "refresh_token": "refresh",
            "expires_at": int(time()) + 3600,
            "user_id": "cookie-user",
            "email": "person@example.com",
        }

    class OtherUserClient:
        async def authenticated_user_id(self, _access_token):
            return "provider-user"

    request = SessionRequest()
    assert await current_user_id(request, OtherUserClient()) is None
    assert request.session == {}
