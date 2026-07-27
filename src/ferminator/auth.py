"""Native Supabase Auth client and server-side browser-session helpers."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from time import time

import httpx
from fastapi import Request

from ferminator.settings import Settings


class AuthenticationError(RuntimeError):
    """A deliberately generic authentication failure safe to show to users."""


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_at: int
    user_id: str
    email: str


def _jwt_payload(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


def _tokens(payload: dict) -> AuthTokens:
    user = payload.get("user") or {}
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    user_id = user.get("id")
    email = user.get("email")
    expires_at = payload.get("expires_at") or _jwt_payload(access_token or "").get("exp")
    if not all((access_token, refresh_token, user_id, email, expires_at)):
        raise AuthenticationError("Unable to sign in.")
    return AuthTokens(
        access_token=str(access_token),
        refresh_token=str(refresh_token),
        expires_at=int(expires_at),
        user_id=str(user_id),
        email=str(email),
    )


class SupabaseAuthClient:
    def __init__(self, settings: Settings):
        if not settings.supabase_url or not settings.supabase_publishable_key:
            raise RuntimeError("Supabase Auth is not configured")
        self.base_url = settings.supabase_url.rstrip("/")
        self.publishable_key = settings.supabase_publishable_key
        self.secret_key = settings.supabase_secret_key

    async def sign_in(self, email: str, password: str) -> AuthTokens:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": self.publishable_key},
                json={"email": email, "password": password},
            )
        if response.status_code != 200:
            raise AuthenticationError("The username or password was not recognized.")
        return _tokens(response.json())

    async def refresh(self, refresh_token: str) -> AuthTokens:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/auth/v1/token",
                params={"grant_type": "refresh_token"},
                headers={"apikey": self.publishable_key},
                json={"refresh_token": refresh_token},
            )
        if response.status_code != 200:
            raise AuthenticationError("Your session expired. Please sign in again.")
        return _tokens(response.json())

    async def sign_out(self, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.base_url}/auth/v1/logout",
                headers={
                    "apikey": self.publishable_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        username: str,
    ) -> str:
        if not self.secret_key:
            raise RuntimeError("SUPABASE_SECRET_KEY is required for account provisioning")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/auth/v1/admin/users",
                headers={
                    "apikey": self.secret_key,
                    "Authorization": f"Bearer {self.secret_key}",
                },
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"username": username},
                },
            )
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"Supabase account creation failed ({response.status_code})")
        return str(response.json()["id"])

    async def delete_user(self, user_id: str) -> None:
        if not self.secret_key:
            return
        async with httpx.AsyncClient(timeout=15) as client:
            await client.delete(
                f"{self.base_url}/auth/v1/admin/users/{user_id}",
                headers={
                    "apikey": self.secret_key,
                    "Authorization": f"Bearer {self.secret_key}",
                },
            )


def save_session(request: Request, tokens: AuthTokens) -> None:
    request.session.clear()
    request.session.update(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at,
            "user_id": tokens.user_id,
            "email": tokens.email,
        }
    )


async def current_user_id(request: Request, client: SupabaseAuthClient) -> str | None:
    user_id = request.session.get("user_id")
    refresh_token = request.session.get("refresh_token")
    expires_at = request.session.get("expires_at")
    if not all((user_id, refresh_token, expires_at)):
        return None
    if int(expires_at) <= int(time()) + 60:
        try:
            save_session(request, await client.refresh(str(refresh_token)))
        except AuthenticationError:
            request.session.clear()
            return None
    return str(request.session["user_id"])
