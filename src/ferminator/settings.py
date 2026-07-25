"""Environment-backed application settings with safe defaults."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    environment: str = "development"
    demo_mode: bool = True
    profile_path: Path = Path("profiles/adam-cagle.md")
    database_url: str | None = None
    auth_mode: str = "off"
    alpha_password: str | None = None
    log_level: str = "INFO"
    public_base_url: str = "http://127.0.0.1:8000"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate_runtime(self) -> None:
        if self.is_production and self.demo_mode:
            raise RuntimeError("FERMINATOR_DEMO_MODE cannot be enabled in production")
        if self.is_production and self.auth_mode == "off":
            raise RuntimeError("FERMINATOR_AUTH_MODE=off is not allowed in production")
        if not self.demo_mode and not self.database_url:
            raise RuntimeError("DATABASE_URL is required when demo mode is disabled")
        if (
            self.environment not in {"development", "test"}
            and not self.demo_mode
            and self.auth_mode == "shared_password"
            and not self.alpha_password
        ):
            raise RuntimeError("FERMINATOR_ALPHA_PASSWORD is required for shared_password")

    def valid_alpha_password(self, candidate: str) -> bool:
        return bool(self.alpha_password) and secrets.compare_digest(
            candidate,
            self.alpha_password,
        )


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    return Settings(
        environment=os.environ.get("FERMINATOR_ENV", "development"),
        demo_mode=_bool_env("FERMINATOR_DEMO_MODE", True),
        profile_path=Path(os.environ.get("FERMINATOR_PROFILE", "profiles/adam-cagle.md")),
        database_url=os.environ.get("DATABASE_URL"),
        auth_mode=os.environ.get("FERMINATOR_AUTH_MODE", "off"),
        alpha_password=os.environ.get("FERMINATOR_ALPHA_PASSWORD"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
        smtp_host=os.environ.get("SMTP_HOST"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_username=os.environ.get("SMTP_USERNAME"),
        smtp_password=os.environ.get("SMTP_PASSWORD"),
        smtp_from=os.environ.get("SMTP_FROM"),
    )
