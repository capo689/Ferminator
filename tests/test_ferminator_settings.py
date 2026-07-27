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


def test_supabase_auth_requires_complete_server_configuration() -> None:
    with pytest.raises(RuntimeError, match="SUPABASE_PUBLISHABLE_KEY"):
        Settings(
            environment="production",
            demo_mode=False,
            database_url="postgresql://example",
            auth_mode="supabase",
            supabase_url="https://example.supabase.co",
            session_secret="x" * 32,
        ).validate_runtime()


def test_production_supabase_auth_requires_strong_session_secret() -> None:
    with pytest.raises(RuntimeError, match="at least 32"):
        Settings(
            environment="production",
            demo_mode=False,
            database_url="postgresql://example",
            auth_mode="supabase",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="sb_publishable_test",
            session_secret="short",
        ).validate_runtime()


def test_production_supabase_auth_requires_https_public_origin() -> None:
    with pytest.raises(RuntimeError, match="production HTTPS origin"):
        Settings(
            environment="production",
            demo_mode=False,
            database_url="postgresql://example",
            auth_mode="supabase",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="sb_publishable_test",
            session_secret="s" * 32,
            public_base_url="http://127.0.0.1:8000",
        ).validate_runtime()
