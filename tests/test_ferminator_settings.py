import pytest

from ferminator.settings import Settings


def test_production_rejects_demo_mode() -> None:
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        Settings(environment="production", demo_mode=True, auth_mode="magic_link").validate_runtime()


def test_production_rejects_missing_auth() -> None:
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        Settings(
            environment="production",
            demo_mode=False,
            database_url="postgresql://example",
            auth_mode="off",
        ).validate_runtime()


def test_live_mode_requires_database() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings(demo_mode=False, auth_mode="off").validate_runtime()


def test_shared_password_uses_constant_time_validation() -> None:
    settings = Settings(auth_mode="shared_password", alpha_password="secret")

    assert settings.valid_alpha_password("secret")
    assert not settings.valid_alpha_password("wrong")
