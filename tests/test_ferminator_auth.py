from time import time

import pytest
import respx
from httpx import Response

from ferminator.auth import AuthenticationError, SupabaseAuthClient
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
